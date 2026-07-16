"""Spark-native CSV normalization adapter."""

from datetime import date
from pathlib import Path
from typing import Any

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import LongType, StringType, StructField, StructType

from .canonical import normalized_text, parse_source_time, required_text
from .contracts import ObjectValidationError, find_variant, read_headers, schema_map

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
    value = F.trim(F.col(source).cast("string"))
    return F.when(F.length(value) == 0, F.lit(None)).otherwise(value).alias(target)


def normalize_object(fixture: Path, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    headers = read_headers(fixture)
    variant = find_variant(headers)
    if metadata.get("variant_key") and metadata["variant_key"] != variant["variant_key"]:
        raise ObjectValidationError("variant_mismatch", "sidecar variant does not match header")
    mapping = schema_map()["field_mappings"][variant["schema_family"]]

    def present(field: str) -> str | None:
        source = mapping[field]
        return source if source in headers else None

    spark = _session()
    schema = StructType([StructField(header, StringType(), True) for header in headers])
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
                _text_column(present("start_ts"), "start_ts_source"),
                _text_column(present("end_ts"), "end_ts_source"),
                _text_column(present("duration"), "duration_source"),
                _text_column(present("start_station_code"), "start_station_code"),
                _text_column(present("start_station_name"), "start_station_name"),
                _text_column(present("end_station_code"), "end_station_code"),
                _text_column(present("end_station_name"), "end_station_name"),
            )
        )
        records = [row.asDict(recursive=False) for row in frame.collect()]
    except Exception as error:
        raise ObjectValidationError("malformed_csv", str(error)) from error
    if len(records) != metadata["expected_source_rows"]:
        raise ObjectValidationError(
            "source_row_count_mismatch",
            f"parsed {len(records)} rows; expected {metadata['expected_source_rows']}",
        )

    period_start = date.fromisoformat(metadata["ownership_period"]["start"])
    period_end = date.fromisoformat(metadata["ownership_period"]["end"])
    normalized = []
    seen = set()
    for record in records:
        rental_id = required_text(record["rental_id"], "rental_id")
        identity = (variant["schema_family"], rental_id)
        if identity in seen:
            raise ObjectValidationError("duplicate_row_identity", f"duplicate identity {identity!r}")
        seen.add(identity)
        start = parse_source_time(record["start_ts_source"], mapping["timestamp_formats"], "start_ts")
        end = parse_source_time(record["end_ts_source"], mapping["timestamp_formats"], "end_ts")
        if not period_start <= start.date() <= period_end:
            raise ObjectValidationError(
                "outside_ownership_period",
                f"start date {start.date()} is outside declared ownership",
            )
        if end <= start:
            raise ObjectValidationError("invalid_timestamp_order", "end_ts must be after start_ts")
        duration_text = required_text(record["duration_source"], "duration")
        try:
            duration = int(duration_text)
        except ValueError as error:
            raise ObjectValidationError("invalid_duration", duration_text) from error
        if duration <= 0:
            raise ObjectValidationError("invalid_duration", duration_text)
        start_code = normalized_text(record["start_station_code"])
        start_name = normalized_text(record["start_station_name"])
        end_code = normalized_text(record["end_station_code"])
        end_name = normalized_text(record["end_station_name"])
        if not (start_code or start_name) or not (end_code or end_name):
            raise ObjectValidationError("invalid_station", "each endpoint needs a code or name")
        normalized.append(
            {
                "schema_family": variant["schema_family"],
                "header_variant_id": metadata["header_variant_id"],
                "rental_id": rental_id,
                "bike_id": required_text(record["bike_id"], "bike_id"),
                "bike_model": normalized_text(record["bike_model"]),
                "start_ts_local": start.isoformat(),
                "end_ts_local": end.isoformat(),
                "source_timezone": "Europe/London",
                "duration_ms": duration * mapping["duration_multiplier"],
                "start_station_code": start_code,
                "start_station_name": start_name,
                "end_station_code": end_code,
                "end_station_name": end_name,
                "source_object_id": metadata["object_id"],
                "ownership_start": metadata["ownership_period"]["start"],
                "ownership_end": metadata["ownership_period"]["end"],
            }
        )
    return normalized


def write_parquet(rows: list[dict[str, Any]], destination: Path) -> None:
    spark = _session()
    spark.createDataFrame(rows, schema=CANONICAL_SCHEMA).coalesce(1).write.mode(
        "overwrite"
    ).parquet(str(destination))
