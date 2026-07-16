"""Container entry point for the independent Spark conformance lane."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCENARIOS = ROOT / "benchmark" / "reliability_reference" / "scenarios"
sys.path.insert(0, str(ROOT))

from benchmark.reliability_reference.cli import run  # noqa: E402
from benchmark.reliability_reference.oracle import assert_expected  # noqa: E402
from benchmark.reliability_reference.runner import run_case  # noqa: E402


def main(output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    report = run("spark", "all", output_root)
    assert report["result"] == "PASS"
    assert len(report["scenarios"]) == 9
    for result_path in sorted((output_root / "results").glob("*.json")):
        assert_expected(json.loads(result_path.read_text(encoding="utf-8")), result_path.stem)
    initial = json.loads(
        (output_root / "results" / "001_initial_variants.json").read_text(encoding="utf-8")
    )
    assert len(initial["canonical_rows"]) == 6
    assert len({row["header_variant_id"] for row in initial["canonical_rows"]}) == 5
    invalid = json.loads(
        (output_root / "results" / "007_invalid_objects.json").read_text(encoding="utf-8")
    )
    assert {
        item["reason_code"]
        for item in invalid["reconciliation"]
        if item["disposition"] == "rejected"
    } == {
        "unknown_header",
        "missing_header",
        "invalid_duration",
        "source_row_count_mismatch",
        "outside_ownership_period",
        "ambiguous_source_time",
        "ownership_period_overlap",
        "duplicate_state_identity",
    }

    clean = run_case(
        "spark",
        SCENARIOS / "009_full_rebuild.json",
        workspace=output_root / "recovery" / "clean",
    )
    recovery = []
    for fault_at in ("after_stage", "after_validation", "before_pointer_swap"):
        workspace = output_root / "recovery" / fault_at
        interrupted = run_case(
            "spark",
            SCENARIOS / "008_interrupted_publish.json",
            workspace=workspace,
            fault_at=fault_at,
        )
        pointer = json.loads((workspace / "current.json").read_text(encoding="utf-8"))
        assert interrupted.terminal_status == "interrupted"
        assert pointer["state_hash"] == interrupted.state_hash
        retry = run_case(
            "spark",
            SCENARIOS / "008_interrupted_publish.json",
            workspace=workspace,
        )
        assert retry.state_hash == clean.state_hash
        assert retry.canonical_rows == clean.canonical_rows
        recovery.append(
            {
                "fault_at": fault_at,
                "pointer_preserved": True,
                "retry_state_hash": retry.state_hash,
                "clean_state_hash": clean.state_hash,
                "result": "PASS",
            }
        )
    (output_root / "spark-recovery.json").write_text(
        json.dumps({"result": "PASS", "faults": recovery}, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
