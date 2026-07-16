"""DuckDB-native typed CSV normalization adapter."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb

from .contracts import ObjectValidationError, find_variant, read_headers, schema_map

LONDON = ZoneInfo("Europe/London")


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _text_expression(source: str | None, target: str) -> str:
    if source is None:
        return f"NULL::VARCHAR AS {_quoted(target)}"
    return f"NULLIF(trim({_quoted(source)}), '') AS {_quoted(target)}"


def _timestamp_expression(source: str, formats: list[str], target: str) -> str:
    attempts = ", ".join(
        f"try_strptime({_quoted(source)}, {_literal(format_string)})"
        for format_string in formats
    )
    return f"coalesce({attempts}) AS {_quoted(target)}"


def _raw_schema(headers: list[str], duration_source: str) -> str:
    fields = []
    for header in headers:
        raw_type = "BIGINT" if header == duration_source else "VARCHAR"
        fields.append(f"{_literal(header)}: {_literal(raw_type)}")
    return "{" + ", ".join(fields) + "}"


def _aware_iso(value: datetime, field: str) -> str:
    candidates = []
    for fold in (0, 1):
        aware = value.replace(tzinfo=LONDON, fold=fold)
        round_trip = aware.astimezone(timezone.utc).astimezone(LONDON).replace(tzinfo=None)
        if round_trip == value:
            candidates.append(aware)
    offsets = {candidate.utcoffset() for candidate in candidates}
    if not candidates:
        raise ObjectValidationError(
            "nonexistent_source_time", f"nonexistent Europe/London {field}: {value!s}"
        )
    if len(offsets) > 1:
        raise ObjectValidationError(
            "ambiguous_source_time", f"ambiguous Europe/London {field}: {value!s}"
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

    expressions = [
        _text_expression(present("rental_id"), "rental_id"),
        _text_expression(present("bike_id"), "bike_id"),
        _text_expression(present("bike_model"), "bike_model"),
        _text_expression(present("start_station_code"), "start_station_code"),
        _text_expression(present("start_station_name"), "start_station_name"),
        _text_expression(present("end_station_code"), "end_station_code"),
        _text_expression(present("end_station_name"), "end_station_name"),
        _timestamp_expression(present("start_ts"), mapping["timestamp_formats"], "start_ts_naive"),
        _timestamp_expression(present("end_ts"), mapping["timestamp_formats"], "end_ts_naive"),
        f"{_quoted(present('duration'))} * {mapping['duration_multiplier']} AS duration_ms",
    ]
    period_start = metadata["ownership_period"]["start"]
    period_end = metadata["ownership_period"]["end"]
    source_schema = _raw_schema(headers, present("duration"))
    query = f"""
        WITH typed AS (
            SELECT {", ".join(expressions)}
            FROM read_csv(?, header=true, columns={source_schema})
        ), profiled AS (
            SELECT *, count(*) OVER (PARTITION BY rental_id) AS identity_count
            FROM typed
        )
        SELECT *, CASE
            WHEN rental_id IS NULL OR bike_id IS NULL THEN 'invalid_required_value'
            WHEN start_ts_naive IS NULL OR end_ts_naive IS NULL THEN 'invalid_timestamp'
            WHEN end_ts_naive <= start_ts_naive THEN 'invalid_timestamp_order'
            WHEN duration_ms IS NULL OR duration_ms <= 0 THEN 'invalid_duration'
            WHEN (start_station_code IS NULL AND start_station_name IS NULL)
              OR (end_station_code IS NULL AND end_station_name IS NULL) THEN 'invalid_station'
            WHEN CAST(start_ts_naive AS DATE) NOT BETWEEN ?::DATE AND ?::DATE
              THEN 'outside_ownership_period'
            WHEN identity_count > 1 THEN 'duplicate_row_identity'
            ELSE NULL
        END AS validation_code
        FROM profiled
    """
    connection = duckdb.connect(":memory:")
    try:
        relation = connection.execute(query, [str(fixture), period_start, period_end])
        columns = [item[0] for item in relation.description]
        records = [dict(zip(columns, values, strict=True)) for values in relation.fetchall()]
    except duckdb.ConversionException as error:
        raise ObjectValidationError("invalid_duration", str(error)) from error
    except duckdb.Error as error:
        raise ObjectValidationError("malformed_csv", str(error)) from error
    finally:
        connection.close()
    if len(records) != metadata["expected_source_rows"]:
        raise ObjectValidationError(
            "source_row_count_mismatch",
            f"parsed {len(records)} rows; expected {metadata['expected_source_rows']}",
        )
    invalid = next((record["validation_code"] for record in records if record["validation_code"]), None)
    if invalid:
        raise ObjectValidationError(invalid, f"DuckDB native validation failed: {invalid}")

    return [
        {
            "schema_family": variant["schema_family"],
            "header_variant_id": metadata["header_variant_id"],
            "rental_id": record["rental_id"],
            "bike_id": record["bike_id"],
            "bike_model": record["bike_model"],
            "start_ts_local": _aware_iso(record["start_ts_naive"], "start_ts"),
            "end_ts_local": _aware_iso(record["end_ts_naive"], "end_ts"),
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
    """Materialize semantic rows without introducing a PyArrow dependency."""
    source = destination.with_name("canonical.json")
    connection = duckdb.connect(":memory:")
    try:
        escaped_source = str(source).replace("'", "''")
        escaped_destination = str(destination).replace("'", "''")
        connection.execute(
            f"COPY (SELECT * FROM read_json_auto('{escaped_source}')) "
            f"TO '{escaped_destination}' (FORMAT PARQUET)"
        )
    finally:
        connection.close()
