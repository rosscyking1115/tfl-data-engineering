import csv
import hashlib
import json
from pathlib import Path

import pytest

from benchmark.gate0.spike.runner import header_variant_id, run_case

ROOT = Path(__file__).parents[1]
GATE0 = ROOT / "benchmark" / "gate0"


def _case(name: str) -> Path:
    return GATE0 / "cases" / f"{name}.json"


def test_header_fingerprint_tracks_ordered_names_not_csv_quoting():
    fields = ("Number", "Start date", "End date")

    assert header_variant_id(fields) == header_variant_id(list(fields))
    assert header_variant_id(fields) != header_variant_id(tuple(reversed(fields)))


def test_duckdb_normalizes_all_five_verified_variants():
    result = run_case("duckdb", _case("normalize-five-variants"))

    assert len(result["canonical_rows"]) == 6
    assert {row["schema_family"] for row in result["canonical_rows"]} == {
        "classic",
        "nextgen",
    }
    assert {row["header_variant_id"] for row in result["canonical_rows"]} == {
        action["header_variant_id"]
        for action in result["reconciliation"]
        if action["action"] == "applied"
    }
    classic_without_code = next(
        row for row in result["canonical_rows"] if row["rental_id"] == "1002"
    )
    assert classic_without_code["end_station_code"] is None
    assert classic_without_code["duration_ms"] == 900_000
    nextgen = next(row for row in result["canonical_rows"] if row["rental_id"] == "2001")
    assert nextgen["start_station_code"] == "001020"
    assert nextgen["start_ts_local"] == "2026-01-01T08:00:00+00:00"


def test_exact_duplicate_replay_is_a_state_noop():
    result = run_case("duckdb", _case("duplicate-replay"))

    first, replay = result["reconciliation"]
    assert first["action"] == "applied"
    assert replay["action"] == "duplicate"
    assert replay["state_hash_before"] == replay["state_hash_after"] == result["state_hash"]
    assert len(result["canonical_rows"]) == 2


def test_constructed_correction_replaces_entire_ownership_period():
    result = run_case("duckdb", _case("correction-replaces-period"))

    correction = result["reconciliation"][-1]
    assert correction["action"] == "replaced"
    assert correction["removed_rows"] == 2
    assert {row["rental_id"] for row in result["canonical_rows"]} == {"2001", "2005"}
    corrected = next(row for row in result["canonical_rows"] if row["rental_id"] == "2001")
    assert corrected["duration_ms"] == 900_000


def test_incompatible_replacement_preserves_prior_good_state():
    result = run_case("duckdb", _case("incompatible-preserves-state"))

    rejected = result["reconciliation"][-1]
    assert rejected["action"] == "rejected"
    assert rejected["state_hash_before"] == rejected["state_hash_after"] == result["state_hash"]
    assert {row["rental_id"] for row in result["canonical_rows"]} == {"2001", "2002"}


def test_ambiguous_london_source_time_is_rejected_before_utc_derivation():
    result = run_case("duckdb", _case("dst-ambiguity-rejected"))

    assert result["canonical_rows"] == []
    assert result["reconciliation"][0]["action"] == "rejected"
    assert "ambiguous Europe/London local time" in result["reconciliation"][0]["reason"]


@pytest.mark.parametrize(
    "case_name",
    [
        "normalize-five-variants",
        "duplicate-replay",
        "correction-replaces-period",
        "incompatible-preserves-state",
        "dst-ambiguity-rejected",
    ],
)
def test_duckdb_case_matches_committed_expected_output(case_name: str):
    expected_path = GATE0 / "expected" / f"{case_name}.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))

    assert run_case("duckdb", _case(case_name)) == expected


@pytest.mark.parametrize("sidecar", sorted((GATE0 / "fixtures").glob("*.sidecar.json")))
def test_fixture_sidecars_match_bytes_and_declared_header(sidecar: Path):
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    fixture = sidecar.with_name(metadata["file"])
    digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
    with fixture.open(encoding="utf-8-sig", newline="") as handle:
        fields = next(csv.reader(handle))

    assert metadata["content_sha256"] == digest
    assert metadata["header_variant_id"] == header_variant_id(fields)
    assert metadata["evidence_class"] in {"observed", "transformed", "constructed"}
    assert metadata["publication_decision"] != "publish_raw"
