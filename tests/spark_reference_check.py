"""Container entry point for the independent Spark conformance lane."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCENARIOS = ROOT / "benchmark" / "reliability_reference" / "scenarios"
sys.path.insert(0, str(ROOT))

from benchmark.reliability_reference.cli import run  # noqa: E402
from benchmark.reliability_reference.oracle import assert_expected  # noqa: E402


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
    }


if __name__ == "__main__":
    main(Path(sys.argv[1]))
