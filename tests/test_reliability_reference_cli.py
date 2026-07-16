import json
import subprocess
import sys
from pathlib import Path

from benchmark.reliability_reference.constants import MANAGED_SCENARIOS

ROOT = Path(__file__).parents[1]


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "benchmark.reliability_reference", *arguments],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )


def test_validate_command_reports_contract_and_fixture_counts():
    completed = run_cli("validate")

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["result"] == "PASS"
    assert report["contract_version"] == "1"
    assert report["gate0_byte_matches"] == 8
    assert report["scenario_count"] == 10
    assert report["oracle_scenario_count"] == 10


def test_version_command_is_stable():
    completed = run_cli("version")

    assert completed.returncode == 0
    assert completed.stdout.strip() == "0.2.0"


def test_duckdb_all_command_writes_one_result_per_executable_scenario(tmp_path: Path):
    output = tmp_path / "duckdb"

    completed = run_cli(
        "run",
        "--engine",
        "duckdb",
        "--scenario",
        "all",
        "--output",
        str(output),
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads((output / "conformance.json").read_text(encoding="utf-8"))
    assert report["result"] == "PASS"
    assert report["engine"] == "duckdb"
    assert len(report["scenarios"]) == 10
    assert len(list((output / "results").glob("*.json"))) == 10


def test_compare_command_returns_nonzero_and_writes_diagnostics_on_mismatch(tmp_path: Path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    output = tmp_path / "comparison"
    for directory, duration in ((left, 10), (right, 11)):
        (directory / "results").mkdir(parents=True)
        result = {
            "case_id": "case",
            "canonical_rows": [
                {"schema_family": "nextgen", "rental_id": "1", "duration_ms": duration}
            ],
            "reconciliation": [],
            "object_history": [],
            "state_hash": f"sha256:{duration}",
        }
        (directory / "results" / "case.json").write_text(
            json.dumps(result), encoding="utf-8"
        )

    completed = run_cli(
        "compare",
        "--duckdb",
        str(left),
        "--spark",
        str(right),
        "--output",
        str(output),
    )

    assert completed.returncode == 1
    report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
    assert report["result"] == "FAIL"
    assert report["scenarios"][0]["field_mismatches"][0]["field"] == "duration_ms"


def test_compare_managed_uses_portable_result_as_authoritative_oracle(tmp_path: Path):
    portable = tmp_path / "portable"
    managed = tmp_path / "managed"
    output = tmp_path / "comparison"
    for directory in (portable, managed):
        (directory / "results").mkdir(parents=True)
    for case_id in MANAGED_SCENARIOS:
        result = {
            "case_id": case_id,
            "canonical_rows": [
                {"schema_family": "nextgen", "rental_id": case_id, "duration_ms": 10}
            ],
            "reconciliation": [],
            "object_history": [],
            "state_hash": f"sha256:{case_id}",
        }
        for directory, engine in ((portable, "duckdb"), (managed, "delta")):
            (directory / "results" / f"{case_id}.json").write_text(
                json.dumps({**result, "engine": engine}), encoding="utf-8"
            )
    (portable / "results" / "portable_only.json").write_text(
        json.dumps({"case_id": "portable_only"}), encoding="utf-8"
    )

    completed = run_cli(
        "compare-managed",
        "--reference",
        str(portable),
        "--managed",
        str(managed),
        "--output",
        str(output),
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
    assert report["result"] == "PASS"
    assert report["reference_engine"] == "duckdb"
    assert report["managed_engine"] == "delta"
    assert [item["case_id"] for item in report["scenarios"]] == list(MANAGED_SCENARIOS)


def test_compare_managed_fails_for_missing_or_unexpected_managed_scenarios(tmp_path: Path):
    portable = tmp_path / "portable" / "results"
    managed = tmp_path / "managed" / "results"
    portable.mkdir(parents=True)
    managed.mkdir(parents=True)
    result = {
        "canonical_rows": [],
        "reconciliation": [],
        "object_history": [],
        "state_hash": "sha256:empty",
    }
    for case_id in MANAGED_SCENARIOS:
        (portable / f"{case_id}.json").write_text(
            json.dumps({**result, "case_id": case_id}), encoding="utf-8"
        )
    for case_id in MANAGED_SCENARIOS[:-1]:
        (managed / f"{case_id}.json").write_text(
            json.dumps({**result, "case_id": case_id}), encoding="utf-8"
        )
    (managed / "unexpected.json").write_text(
        json.dumps({**result, "case_id": "unexpected"}), encoding="utf-8"
    )

    completed = run_cli(
        "compare-managed",
        "--reference",
        str(portable.parent),
        "--managed",
        str(managed.parent),
        "--output",
        str(tmp_path / "comparison"),
    )

    assert completed.returncode == 1
    report = json.loads(
        (tmp_path / "comparison" / "comparison.json").read_text(encoding="utf-8")
    )
    assert any("missing_managed_result" in item for item in report["scenarios"])
    assert any("unexpected_managed_result" in item for item in report["scenarios"])
