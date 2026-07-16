"""Engine-neutral replay seam for the Gate 0 reliability-reference spike."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

GATE0_ROOT = Path(__file__).parents[1]
CONTRACT_PATH = GATE0_ROOT / "contracts" / "schema-map.json"
FIXTURE_ROOT = GATE0_ROOT / "fixtures"
LONDON = ZoneInfo("Europe/London")


class Gate0ValidationError(ValueError):
    """Expected object-level rejection that must leave prior state unchanged."""


class FixtureIntegrityError(ValueError):
    """Committed fixture bytes do not match their provenance sidecar."""


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def header_variant_id(fields: list[str] | tuple[str, ...]) -> str:
    """Return the exact ordered-field fingerprint, independent of CSV quoting."""
    payload = json.dumps(list(fields), ensure_ascii=False, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _state_hash(rows: list[dict[str, Any]]) -> str:
    payload = _stable_json(sorted(rows, key=_row_sort_key)).encode()
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _row_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return row["schema_family"], row["rental_id"], row["start_ts_local"]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_duckdb(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    import duckdb

    with duckdb.connect() as connection:
        cursor = connection.execute(
            "SELECT * FROM read_csv(?, header=true, all_varchar=true, sample_size=-1)",
            [str(path)],
        )
        fields = [item[0] for item in cursor.description]
        rows = [dict(zip(fields, values, strict=True)) for values in cursor.fetchall()]
    return fields, rows


def _read_spark(path: Path, spark: Any) -> tuple[list[str], list[dict[str, Any]]]:
    frame = (
        spark.read.option("header", True)
        .option("inferSchema", False)
        .option("mode", "FAILFAST")
        .option("enforceSchema", False)
        .csv(str(path))
    )
    fields = list(frame.columns)
    rows = [row.asDict(recursive=False) for row in frame.collect()]
    return fields, rows


def _parse_source_time(value: Any, formats: list[str], field: str) -> datetime:
    text = _required_text(value, field)
    parsed = None
    for format_string in formats:
        try:
            parsed = datetime.strptime(text, format_string)
            break
        except ValueError:
            continue
    if parsed is None:
        raise Gate0ValidationError(f"{field}: unsupported timestamp {text!r}")

    candidates = []
    for fold in (0, 1):
        aware = parsed.replace(tzinfo=LONDON, fold=fold)
        round_trip = aware.astimezone(timezone.utc).astimezone(LONDON).replace(tzinfo=None)
        if round_trip == parsed:
            candidates.append(aware)
    offsets = {candidate.utcoffset() for candidate in candidates}
    if not candidates:
        raise Gate0ValidationError(f"{field}: nonexistent Europe/London local time {text!r}")
    if len(offsets) > 1:
        raise Gate0ValidationError(f"{field}: ambiguous Europe/London local time {text!r}")
    return candidates[0]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().split())
    return normalized or None


def _required_text(value: Any, field: str) -> str:
    normalized = _text(value)
    if normalized is None:
        raise Gate0ValidationError(f"{field}: required value is null")
    return normalized


def _positive_integer(value: Any, field: str) -> int:
    text = _required_text(value, field)
    try:
        number = int(text)
    except ValueError as error:
        raise Gate0ValidationError(f"{field}: expected integer, got {text!r}") from error
    if number <= 0:
        raise Gate0ValidationError(f"{field}: expected positive integer, got {number}")
    return number


def _find_variant(contract: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    for variant in contract["variants"]:
        if variant["headers"] == fields:
            return variant
    raise Gate0ValidationError(f"incompatible ordered header: {fields!r}")


def _normalize_rows(
    rows: list[dict[str, Any]],
    variant: dict[str, Any],
    metadata: dict[str, Any],
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    family = variant["schema_family"]
    mapping = contract["field_mappings"][family]
    period_start = date.fromisoformat(metadata["ownership_period"]["start"])
    period_end = date.fromisoformat(metadata["ownership_period"]["end"])
    variant_id = header_variant_id(variant["headers"])
    normalized = []
    seen_keys: set[tuple[str, str]] = set()

    for source in rows:
        rental_id = _required_text(source.get(mapping["rental_id"]), "rental_id")
        key = family, rental_id
        if key in seen_keys:
            raise Gate0ValidationError(f"duplicate rental identity within object: {key!r}")
        seen_keys.add(key)

        start = _parse_source_time(source.get(mapping["start_ts"]), mapping["timestamp_formats"], "start_ts")
        end = _parse_source_time(source.get(mapping["end_ts"]), mapping["timestamp_formats"], "end_ts")
        if not period_start <= start.date() <= period_end:
            raise Gate0ValidationError(
                f"start_ts {start.date().isoformat()} is outside declared ownership period"
            )
        if end <= start:
            raise Gate0ValidationError("end_ts must be later than start_ts")

        duration = _positive_integer(source.get(mapping["duration"]), "duration")
        start_code = _text(source.get(mapping["start_station_code"]))
        start_name = _text(source.get(mapping["start_station_name"]))
        end_code = _text(source.get(mapping["end_station_code"]))
        end_name = _text(source.get(mapping["end_station_name"]))
        if not (start_code or start_name) or not (end_code or end_name):
            raise Gate0ValidationError("each journey endpoint requires a station code or name")

        normalized.append(
            {
                "schema_family": family,
                "header_variant_id": variant_id,
                "rental_id": rental_id,
                "bike_id": _required_text(source.get(mapping["bike_id"]), "bike_id"),
                "bike_model": _text(source.get(mapping["bike_model"])) if mapping["bike_model"] else None,
                "start_ts_local": start.isoformat(),
                "end_ts_local": end.isoformat(),
                "source_timezone": contract["canonical_timezone"],
                "duration_ms": duration * mapping["duration_multiplier"],
                "start_station_code": start_code,
                "start_station_name": start_name,
                "end_station_code": end_code,
                "end_station_name": end_name,
                "source_object_id": metadata["object_id"],
            }
        )
    return normalized


def _validate_integrity(metadata: dict[str, Any], fixture: Path) -> str:
    actual = _file_sha256(fixture)
    if metadata.get("content_sha256") != actual:
        raise FixtureIntegrityError(
            f"{fixture.name}: sidecar sha256 {metadata.get('content_sha256')!r} != {actual!r}"
        )
    return actual


def _period_contains(row: dict[str, Any], metadata: dict[str, Any]) -> bool:
    start = metadata["ownership_period"]["start"]
    end = metadata["ownership_period"]["end"]
    row_date = row["start_ts_local"][:10]
    return start <= row_date <= end


def run_case(engine: str, case_definition: str | Path | dict[str, Any]) -> dict[str, Any]:
    """Run one case and return canonical rows, reconciliation, and semantic state hash."""
    if engine not in {"duckdb", "spark"}:
        raise ValueError(f"unsupported engine {engine!r}; expected 'duckdb' or 'spark'")
    case = _load_json(Path(case_definition)) if not isinstance(case_definition, dict) else case_definition
    contract = _load_json(CONTRACT_PATH)
    state: dict[tuple[str, str], dict[str, Any]] = {}
    applied_hashes: set[str] = set()
    applied_objects: dict[str, dict[str, Any]] = {}
    reconciliation = []
    spark = None
    if engine == "spark":
        from pyspark.sql import SparkSession

        spark = (
            SparkSession.builder.master("local[2]")
            .appName(f"gate0-{case['case_id']}")
            .config("spark.sql.session.timeZone", "Europe/London")
            .getOrCreate()
        )

    try:
        for sidecar_name in case["objects"]:
            metadata = _load_json(FIXTURE_ROOT / sidecar_name)
            fixture = FIXTURE_ROOT / metadata["file"]
            content_hash = _validate_integrity(metadata, fixture)
            before_rows = sorted(state.values(), key=_row_sort_key)
            before_hash = _state_hash(before_rows)
            base = {
                "object_id": metadata["object_id"],
                "content_sha256": content_hash,
                "header_variant_id": metadata["header_variant_id"],
                "state_hash_before": before_hash,
                "removed_rows": 0,
            }
            if content_hash in applied_hashes:
                reconciliation.append(
                    {
                        **base,
                        "action": "duplicate",
                        "input_rows": 0,
                        "accepted_rows": 0,
                        "rejected_rows": 0,
                        "reason": "exact content hash already applied",
                        "state_hash_after": before_hash,
                    }
                )
                continue

            fields, source_rows = (
                _read_duckdb(fixture) if engine == "duckdb" else _read_spark(fixture, spark)
            )
            actual_variant_id = header_variant_id(fields)
            if metadata["header_variant_id"] != actual_variant_id:
                raise FixtureIntegrityError(
                    f"{fixture.name}: sidecar header fingerprint does not match fixture header"
                )
            try:
                variant = _find_variant(contract, fields)
                if metadata.get("variant_key") != variant["variant_key"]:
                    raise FixtureIntegrityError(
                        f"{fixture.name}: sidecar variant_key does not match schema contract"
                    )
                if metadata.get("schema_family") != variant["schema_family"]:
                    raise FixtureIntegrityError(
                        f"{fixture.name}: sidecar schema_family does not match schema contract"
                    )
                candidate_rows = _normalize_rows(source_rows, variant, metadata, contract)
                supersedes = metadata.get("supersedes")
                if supersedes:
                    previous = applied_objects.get(supersedes)
                    if previous is None:
                        raise Gate0ValidationError(f"superseded object {supersedes!r} is not active")
                    if previous["ownership_period"] != metadata["ownership_period"]:
                        raise Gate0ValidationError("replacement ownership period differs from prior object")
            except Gate0ValidationError as error:
                reconciliation.append(
                    {
                        **base,
                        "header_variant_id": actual_variant_id,
                        "action": "rejected",
                        "input_rows": len(source_rows),
                        "accepted_rows": 0,
                        "rejected_rows": len(source_rows),
                        "reason": str(error),
                        "state_hash_after": before_hash,
                    }
                )
                continue

            removed = 0
            action = "applied"
            if metadata.get("supersedes"):
                keys_to_remove = [key for key, row in state.items() if _period_contains(row, metadata)]
                for key in keys_to_remove:
                    del state[key]
                removed = len(keys_to_remove)
                action = "replaced"
            for row in candidate_rows:
                state[(row["schema_family"], row["rental_id"])] = row
            applied_hashes.add(content_hash)
            applied_objects[metadata["object_id"]] = metadata
            after_hash = _state_hash(list(state.values()))
            reconciliation.append(
                {
                    **base,
                    "header_variant_id": actual_variant_id,
                    "action": action,
                    "input_rows": len(source_rows),
                    "accepted_rows": len(candidate_rows),
                    "rejected_rows": 0,
                    "removed_rows": removed,
                    "reason": "",
                    "state_hash_after": after_hash,
                }
            )
    finally:
        if spark is not None:
            spark.stop()

    canonical_rows = sorted(state.values(), key=_row_sort_key)
    return {
        "case_id": case["case_id"],
        "engine": engine,
        "canonical_rows": canonical_rows,
        "reconciliation": reconciliation,
        "state_hash": _state_hash(canonical_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("duckdb", "spark"), required=True)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_case(args.engine, args.case)
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
