"""Independent Databricks Spark DataFrame normalizer for constructed fixtures."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .contracts import ObjectValidationError, find_variant, read_headers, schema_map

LONDON = ZoneInfo("Europe/London")
SPARK_TIMESTAMP_FORMATS = {
    "%d/%m/%Y %H:%M": "dd/MM/yyyy HH:mm",
    "%Y-%m-%d %H:%M": "yyyy-MM-dd HH:mm",
    "%Y-%m-%d %H:%M:%S": "yyyy-MM-dd HH:mm:ss",
}


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


def normalize_object(
    spark: Any, fixture: Path, metadata: dict[str, Any]
) -> list[dict[str, Any]]:
    """Normalize one complete object without importing the local Spark adapter."""

    from pyspark.sql import functions as F
    from pyspark.sql.types import LongType, StringType, StructField, StructType
    from pyspark.sql.window import Window

    spark.conf.set("spark.sql.session.timeZone", "Europe/London")
    headers = read_headers(fixture)
    variant = find_variant(headers)
    if metadata.get("variant_key") and metadata["variant_key"] != variant["variant_key"]:
        raise ObjectValidationError("variant_mismatch", "sidecar variant does not match header")
    mapping = schema_map()["field_mappings"][variant["schema_family"]]

    def present(field: str) -> str | None:
        source = mapping[field]
        return source if source in headers else None

    def text_column(source: str | None, target: str):
        if source is None:
            return F.lit(None).cast("string").alias(target)
        value = F.regexp_replace(F.trim(F.col(source).cast("string")), r"\s+", " ")
        return F.when(F.length(value) == 0, F.lit(None)).otherwise(value).alias(target)

    def parsed_timestamp(source: str, formats: list[str], target: str):
        attempts = [F.to_timestamp(F.col(source), SPARK_TIMESTAMP_FORMATS[item]) for item in formats]
        return F.coalesce(*attempts).alias(target)

    duration_source = present("duration")
    if duration_source is None:
        raise ObjectValidationError("missing_header", "duration header is absent")
    start_source = present("start_ts")
    end_source = present("end_ts")
    if start_source is None or end_source is None:
        raise ObjectValidationError("missing_header", "timestamp header is absent")
    schema = StructType([StructField(header, StringType(), True) for header in headers])
    try:
        with fixture.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            parsed_headers = next(reader)
            if parsed_headers != headers:
                raise ObjectValidationError(
                    "header_changed_during_read", "fixture header changed during validation"
                )
            raw_rows = []
            for row_number, row in enumerate(reader, start=2):
                if len(row) != len(headers):
                    raise ObjectValidationError(
                        "malformed_csv",
                        f"row {row_number} has {len(row)} values; expected {len(headers)}",
                    )
                raw_rows.append(tuple(row))
        frame = (
            spark.createDataFrame(raw_rows, schema=schema)
            .select(
                text_column(present("rental_id"), "rental_id"),
                text_column(present("bike_id"), "bike_id"),
                text_column(present("bike_model"), "bike_model"),
                text_column(present("start_station_code"), "start_station_code"),
                text_column(present("start_station_name"), "start_station_name"),
                text_column(present("end_station_code"), "end_station_code"),
                text_column(present("end_station_name"), "end_station_name"),
                text_column(start_source, "start_ts_source"),
                text_column(end_source, "end_ts_source"),
                parsed_timestamp(start_source, mapping["timestamp_formats"], "start_ts_naive"),
                parsed_timestamp(end_source, mapping["timestamp_formats"], "end_ts_naive"),
                (F.col(duration_source).cast(LongType()) * F.lit(mapping["duration_multiplier"]))
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
    except ObjectValidationError:
        raise
    except (csv.Error, StopIteration) as error:
        raise ObjectValidationError("malformed_csv", str(error)) from error
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
        raise ObjectValidationError(invalid_code, f"Delta validation failed: {invalid_code}")

    period = metadata["ownership_period"]
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
            "ownership_start": period["start"],
            "ownership_end": period["end"],
        }
        for record in records
    ]
