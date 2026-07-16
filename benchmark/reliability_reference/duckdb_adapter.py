"""DuckDB-native CSV normalization adapter."""

from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from .canonical import normalized_text, parse_source_time, required_text
from .contracts import ObjectValidationError, find_variant, read_headers, schema_map


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _text_expression(source: str | None, target: str) -> str:
    if source is None:
        return f"NULL::VARCHAR AS {_quoted(target)}"
    return f"NULLIF(trim(CAST({_quoted(source)} AS VARCHAR)), '') AS {_quoted(target)}"


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
        _text_expression(present("start_ts"), "start_ts_source"),
        _text_expression(present("end_ts"), "end_ts_source"),
        _text_expression(present("duration"), "duration_source"),
        _text_expression(present("start_station_code"), "start_station_code"),
        _text_expression(present("start_station_name"), "start_station_name"),
        _text_expression(present("end_station_code"), "end_station_code"),
        _text_expression(present("end_station_name"), "end_station_name"),
    ]
    connection = duckdb.connect(":memory:")
    try:
        relation = connection.execute(
            f"SELECT {', '.join(expressions)} FROM read_csv(?, header=true, all_varchar=true)",
            [str(fixture)],
        )
        columns = [item[0] for item in relation.description]
        records = [dict(zip(columns, values, strict=True)) for values in relation.fetchall()]
    except duckdb.Error as error:
        raise ObjectValidationError("malformed_csv", str(error)) from error
    finally:
        connection.close()
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
