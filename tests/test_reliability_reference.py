import json
from pathlib import Path

import pytest

from benchmark.reliability_reference import CONTRACT_VERSION, VERSION, RunResult, run_case
from benchmark.reliability_reference.compare import compare_results
from benchmark.reliability_reference.contracts import ContractError, validate_fixture_pack
from benchmark.reliability_reference.oracle import assert_expected

ROOT = Path(__file__).parents[1]
REFERENCE = ROOT / "benchmark" / "reliability_reference"
SCENARIOS = REFERENCE / "scenarios"


def scenario(name: str) -> Path:
    return SCENARIOS / f"{name}.json"


def test_candidate_version_and_fixture_pack_are_frozen_from_gate0():
    report = validate_fixture_pack()

    assert VERSION == "0.2.0"
    assert CONTRACT_VERSION == "1"
    assert report["fixture_count"] == 8
    assert report["total_fixture_count"] == 14
    assert report["gate0_byte_matches"] == 8
    assert report["publication_decisions"] == {"publish_constructed": 14}


def test_duckdb_normalizes_all_five_verified_header_variants(tmp_path: Path):
    result = run_case("duckdb", scenario("001_initial_variants"), workspace=tmp_path)

    assert isinstance(result, RunResult)
    assert result.terminal_status == "success"
    assert len(result.canonical_rows) == 6
    assert {row["schema_family"] for row in result.canonical_rows} == {
        "classic",
        "nextgen",
    }
    assert len({row["header_variant_id"] for row in result.canonical_rows}) == 5
    missing_code = next(row for row in result.canonical_rows if row["rental_id"] == "1002")
    assert missing_code["end_station_code"] is None
    assert missing_code["duration_ms"] == 900_000
    assert "T" in missing_code["start_ts_local"]
    assert missing_code["start_ts_local"].endswith("+01:00")


def test_exact_duplicate_is_recorded_without_changing_visible_state(tmp_path: Path):
    result = run_case("duckdb", scenario("002_duplicate_replay"), workspace=tmp_path)

    first, replay = result.reconciliation
    assert first["disposition"] == "accepted"
    assert replay["disposition"] == "duplicate"
    assert replay["state_hash_before"] == replay["state_hash_after"] == result.state_hash
    assert len(result.canonical_rows) == 2


def test_correction_replaces_the_complete_declared_period(tmp_path: Path):
    result = run_case("duckdb", scenario("004_corrected_period"), workspace=tmp_path)

    correction = result.reconciliation[-1]
    assert correction["disposition"] == "replaced"
    assert correction["removed_rows"] == 2
    assert {row["rental_id"] for row in result.canonical_rows} == {"2001", "2005"}
    corrected = next(row for row in result.canonical_rows if row["rental_id"] == "2001")
    assert corrected["duration_ms"] == 900_000


def test_late_arrival_is_order_independent_and_matches_full_rebuild(tmp_path: Path):
    late = run_case("duckdb", scenario("005_late_arrival"), workspace=tmp_path / "late")
    rebuild = run_case("duckdb", scenario("009_full_rebuild"), workspace=tmp_path / "rebuild")

    assert late.state_hash == rebuild.state_hash
    assert late.canonical_rows == rebuild.canonical_rows


def test_unknown_missing_malformed_truncated_out_of_period_and_dst_reject_atomically(
    tmp_path: Path,
):
    result = run_case("duckdb", scenario("007_invalid_objects"), workspace=tmp_path)

    rejected = [item for item in result.reconciliation if item["disposition"] == "rejected"]
    assert {item["reason_code"] for item in rejected} == {
        "unknown_header",
        "missing_header",
        "invalid_duration",
        "source_row_count_mismatch",
        "outside_ownership_period",
        "ambiguous_source_time",
    }
    assert len(result.canonical_rows) == 2
    assert all(item["state_hash_before"] == item["state_hash_after"] for item in rejected)
    assert all(item["quarantined_rows"] == 0 for item in rejected)


@pytest.mark.parametrize(
    "fault_at",
    ["after_stage", "after_validation", "before_pointer_swap"],
)
def test_interrupted_publish_preserves_pointer_and_retry_matches_clean_run(
    tmp_path: Path,
    fault_at: str,
):
    workspace = tmp_path / fault_at
    interrupted = run_case(
        "duckdb",
        scenario("008_interrupted_publish"),
        workspace=workspace,
        fault_at=fault_at,
    )
    pointer_after_failure = json.loads((workspace / "current.json").read_text(encoding="utf-8"))

    assert interrupted.terminal_status == "interrupted"
    assert pointer_after_failure["state_hash"] == interrupted.state_hash
    assert {row["rental_id"] for row in interrupted.canonical_rows} == {"2001", "2002"}

    retry = run_case("duckdb", scenario("008_interrupted_publish"), workspace=workspace)
    clean = run_case(
        "duckdb",
        scenario("009_full_rebuild"),
        workspace=tmp_path / f"clean-{fault_at}",
    )

    assert retry.terminal_status == "success"
    assert retry.state_hash == clean.state_hash
    assert retry.canonical_rows == clean.canonical_rows


@pytest.mark.parametrize("protected", ["fixtures", "expected"])
def test_runner_refuses_committed_contract_directories_as_workspace(protected: str):
    with pytest.raises(ContractError, match="committed benchmark assets"):
        run_case(
            "duckdb",
            scenario("002_duplicate_replay"),
            workspace=REFERENCE / protected,
        )


def test_comparator_reports_field_level_semantic_mismatch():
    expected = {
        "case_id": "case",
        "canonical_rows": [{"schema_family": "nextgen", "rental_id": "1", "duration_ms": 10}],
        "reconciliation": [],
        "object_history": [],
        "state_hash": "sha256:expected",
    }
    actual = {
        **expected,
        "canonical_rows": [{"schema_family": "nextgen", "rental_id": "1", "duration_ms": 11}],
        "state_hash": "sha256:actual",
    }

    report = compare_results(expected, actual)

    assert report["result"] == "FAIL"
    assert report["field_mismatches"] == [
        {
            "identity": ["nextgen", "1"],
            "field": "duration_ms",
            "expected": 10,
            "actual": 11,
        }
    ]


def test_run_result_is_json_serializable(tmp_path: Path):
    result = run_case("duckdb", scenario("003_new_period"), workspace=tmp_path)

    rendered = json.dumps(result.to_dict(), ensure_ascii=False)

    assert '"benchmark_version": "0.2.0"' in rendered
    assert all(not Path(path).is_absolute() for path in result.artifacts.values())


@pytest.mark.parametrize(
    "scenario_name",
    [
        "001_initial_variants",
        "002_duplicate_replay",
        "003_new_period",
        "004_corrected_period",
        "005_late_arrival",
        "006_header_compatibility",
        "007_invalid_objects",
        "008_interrupted_publish",
        "009_full_rebuild",
    ],
)
def test_duckdb_matches_human_reviewed_oracle(tmp_path: Path, scenario_name: str):
    result = run_case("duckdb", scenario(scenario_name), workspace=tmp_path)

    assert_expected(result.to_dict(), scenario_name)
