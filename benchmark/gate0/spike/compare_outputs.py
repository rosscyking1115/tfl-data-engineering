"""Compare containerized Spark results with committed DuckDB expected outputs."""

import json
from datetime import datetime, timezone

from .generate_expected import CASE_NAMES
from .runner import GATE0_ROOT

ROOT = GATE0_ROOT.parents[1]
REPORT = ROOT / "docs" / "gate0" / "reliability-reference" / "cross-engine-results.json"


def _semantic(result: dict) -> dict:
    return {key: value for key, value in result.items() if key != "engine"}


def main() -> None:
    results = []
    for case_name in CASE_NAMES:
        expected_path = GATE0_ROOT / "expected" / f"{case_name}.json"
        spark_path = GATE0_ROOT / "evidence" / "spark" / f"{case_name}.json"
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        spark = json.loads(spark_path.read_text(encoding="utf-8"))
        matches = _semantic(expected) == _semantic(spark)
        results.append(
            {
                "case_id": case_name,
                "duckdb_state_hash": expected["state_hash"],
                "spark_state_hash": spark["state_hash"],
                "semantic_match": matches,
            }
        )
        if not matches:
            raise SystemExit(f"cross-engine mismatch: {case_name}")
    report = {
        "observed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "duckdb_version": "1.5.4",
        "spark_image": "apache/spark:4.0.1-java21-python3",
        "declared_comparison": "ordered canonical rows, reconciliation, and state hash",
        "result": "PASS",
        "cases": results,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{len(results)} cross-engine cases PASS -> {REPORT}")


if __name__ == "__main__":
    main()
