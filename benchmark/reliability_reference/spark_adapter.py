"""Spark-native typed CSV normalization adapter."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import LongType, StringType, StructField, StructType
from pyspark.sql.window import Window

from .contracts import ObjectValidationError, find_variant, read_headers, schema_map

LONDON = ZoneInfo("Europe/London")
SPARK_TIMESTAMP_FORMATS = {
    "%d/%m/%Y %H:%M": "dd/MM/yyyy HH:mm",
    "%Y-%m-%d %H:%M": "yyyy-MM-dd HH:mm",
    "%Y-%m-%d %H:%M:%S": "yyyy-MM-dd HH:mm:ss",
}

CANONICAL_SCHEMA = StructType(
    [
        StructField("schema_family", StringType(), False),
        StructField("header_variant_id", StringType(), False),
        StructField("rental_id", StringType(), False),
        StructField("bike_id", StringType(), False),
        StructField("bike_model", StringType(), True),
        StructField("start_ts_local", StringType(), False),
        StructField("end_ts_local", StringType(), False),
        StructField("source_timezone", StringType(), False),
        StructField("duration_ms", LongType(), False),
        StructField("start_station_code", StringType(), True),
        StructField("start_station_name", StringType(), True),
        StructField("end_station_code", StringType(), True),
        StructField("end_station_name", StringType(), True),
        StructField("source_object_id", StringType(), False),
        StructField("ownership_start", StringType(), False),
        StructField("ownership_end", StringType(), False),
    ]
)


def _session() -> SparkSession:
    session = (
        SparkSession.builder.master("local[2]")
        .appName("tfl-reliability-reference")
        .config("spark.sql.session.timeZone", "Europe/London")
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    return session


def _text_column(source: str | None, target: str):
    if source is None:
        return F.lit(None).cast("string").alias(target)
    value = F.regexp_replace(F.trim(F.col(source).cast("string")), r"\s+", " ")
    return F.when(F.length(value) == 0, F.lit(None)).otherwise(value).alias(target)


def _parsed_timestamp(source: str, formats: list[str], target: str):
    attempts = [F.to_timestamp(F.col(source), SPARK_TIMESTAMP_FORMATS[item]) for item in formats]
    return F.coalesce(*attempts).alias(target)


def _aware_iso(value: str, formats: list[str], field: str) -> str:
    parsed = None
    for format_string in formats:
        try:
            parsed = datetime.strptime(value, format_string)
            break
        except ValueError:
            continue
    if parsed is None:
        raise ObjectValidationError("invalid_timestamp", f"unsupported {field}: {value!r}")
    candidates = []
    for fold in (0, 1):
        aware = parsed.replace(tzinfo=LONDON, fold=fold)
        round_trip = aware.astimezone(timezone.utc).astimezone(LONDON).replace(tzinfo=None)
        if round_trip == parsed:
            candidates.append(aware)
    offsets = {candidate.utcoffset() for candidate in candidates}
    if not candidates:
        raise ObjectValidationError(
            "nonexistent_source_time", f"nonexistent Europe/London {field}: {value!r}"
        )
    if len(offsets) > 1:
        raise ObjectValidationError(
            "ambiguous_source_time", f"ambiguous Europe/London {field}: {value!r}"
        )
    return candidates[0].isoformat()


def normalize_object(fixture: Path, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    headers = read_headers(fixture)
    variant = find_variant(headers)
    if metadata.get("variant_key") and metadata["variant_key"] != variant["variant_key"]:
        raise ObjectValidationError("variant_mismatch", "sidecar variant does not match header")
    mapping = schema_map()["field_mappings"][variant["schema_family"]]

    def present(field: str) -> str | None:
        source = mapping[field]
        return source if source in headers else None

    duration_source = present("duration")
    schema = StructType(
        [
            StructField(
                header,
                LongType() if header == duration_source else StringType(),
                True,
            )
            for header in headers
        ]
    )
    spark = _session()
    try:
        frame = (
            spark.read.option("header", True)
            .option("mode", "FAILFAST")
            .option("enforceSchema", False)
            .schema(schema)
            .csv(str(fixture))
            .select(
                _text_column(present("rental_id"), "rental_id"),
                _text_column(present("bike_id"), "bike_id"),
                _text_column(present("bike_model"), "bike_model"),
                _text_column(present("start_station_code"), "start_station_code"),
                _text_column(present("start_station_name"), "start_station_name"),
                _text_column(present("end_station_code"), "end_station_code"),
                _text_column(present("end_station_name"), "end_station_name"),
                _text_column(present("start_ts"), "start_ts_source"),
                _text_column(present("end_ts"), "end_ts_source"),
                _parsed_timestamp(present("start_ts"), mapping["timestamp_formats"], "start_ts_naive"),
                _parsed_timestamp(present("end_ts"), mapping["timestamp_formats"], "end_ts_naive"),
                (F.col(duration_source) * F.lit(mapping["duration_multiplier"]))
                .cast("long")
                .alias("duration_ms"),
            )
        )
        profiled = frame.withColumn(
            "identity_count", F.count(F.lit(1)).over(Window.partitionBy("rental_id"))
        )
        invalid = (
            F.when(F.col("rental_id").isNull() | F.col("bike_id").isNull(), "invalid_required_value")
            .when(
                F.col("start_ts_naive").isNull() | F.col("end_ts_naive").isNull(),
                "invalid_timestamp",
            )
            .when(F.col("end_ts_naive") <= F.col("start_ts_naive"), "invalid_timestamp_order")
            .when(F.col("duration_ms").isNull() | (F.col("duration_ms") <= 0), "invalid_duration")
            .when(
                (F.col("start_station_code").isNull() & F.col("start_station_name").isNull())
                | (F.col("end_station_code").isNull() & F.col("end_station_name").isNull()),
                "invalid_station",
            )
            .when(
                ~F.to_date("start_ts_naive").between(
                    F.lit(metadata["ownership_period"]["start"]).cast("date"),
                    F.lit(metadata["ownership_period"]["end"]).cast("date"),
                ),
                "outside_ownership_period",
            )
            .when(F.col("identity_count") > 1, "duplicate_row_identity")
        )
        records = [
            row.asDict(recursive=False)
            for row in profiled.withColumn("validation_code", invalid).collect()
        ]
    except Exception as error:
        message = str(error)
        if duration_source in message or "NumberFormatException" in message:
            raise ObjectValidationError("invalid_duration", message) from error
        raise ObjectValidationError("malformed_csv", message) from error
    if len(records) != metadata["expected_source_rows"]:
        raise ObjectValidationError(
            "source_row_count_mismatch",
            f"parsed {len(records)} rows; expected {metadata['expected_source_rows']}",
        )
    invalid_code = next(
        (record["validation_code"] for record in records if record["validation_code"]), None
    )
    if invalid_code:
        raise ObjectValidationError(invalid_code, f"Spark native validation failed: {invalid_code}")

    period_start = metadata["ownership_period"]["start"]
    period_end = metadata["ownership_period"]["end"]
    return [
        {
            "schema_family": variant["schema_family"],
            "header_variant_id": metadata["header_variant_id"],
            "rental_id": record["rental_id"],
            "bike_id": record["bike_id"],
            "bike_model": record["bike_model"],
            "start_ts_local": _aware_iso(
                record["start_ts_source"], mapping["timestamp_formats"], "start_ts"
            ),
            "end_ts_local": _aware_iso(
                record["end_ts_source"], mapping["timestamp_formats"], "end_ts"
            ),
            "source_timezone": "Europe/London",
            "duration_ms": record["duration_ms"],
            "start_station_code": record["start_station_code"],
            "start_station_name": record["start_station_name"],
            "end_station_code": record["end_station_code"],
            "end_station_name": record["end_station_name"],
            "source_object_id": metadata["object_id"],
            "ownership_start": period_start,
            "ownership_end": period_end,
        }
        for record in records
    ]


def write_parquet(rows: list[dict[str, Any]], destination: Path) -> None:
    spark = _session()
    spark.createDataFrame(rows, schema=CANONICAL_SCHEMA).coalesce(1).write.mode(
        "overwrite"
    ).parquet(str(destination))
