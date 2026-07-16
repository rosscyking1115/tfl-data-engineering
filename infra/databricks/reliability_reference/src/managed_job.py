"""Execute the bounded constructed-fixture proof in a Databricks job."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    starts = [Path(__file__).resolve(), Path.cwd().resolve()]
    for start in starts:
        for parent in (start, *start.parents):
            if (parent / "benchmark" / "reliability_reference").is_dir():
                return parent
    raise RuntimeError("synced reliability-reference package is unavailable")


REPO_ROOT = _repo_root()
sys.path.insert(0, str(REPO_ROOT))

from benchmark.reliability_reference.constants import MANAGED_SCENARIOS  # noqa: E402
from benchmark.reliability_reference.delta_runner import (  # noqa: E402
    DeltaStateStore,
    run_managed_case,
)
from benchmark.reliability_reference.managed_evidence import (  # noqa: E402
    redact_evidence,
    resource_names,
    validate_managed_scenario_results,
)

SCENARIO_ROOT = REPO_ROOT / "benchmark" / "reliability_reference" / "scenarios"
FAULTS = ("after_stage", "after_validation", "before_pointer_swap")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _history(spark: Any, store: DeltaStateStore) -> dict[str, list[dict[str, Any]]]:
    evidence: dict[str, list[dict[str, Any]]] = {}
    for table in store.names.all():
        table_key = table.rsplit(".", 1)[-1].replace("`", "")
        rows = spark.sql(f"DESCRIBE HISTORY {table} LIMIT 20").collect()
        evidence[table_key] = [
            {
                key: value
                for key, value in row.asDict(recursive=True).items()
                if key in {"version", "operation", "operationParameters", "isBlindAppend"}
            }
            for row in rows
        ]
    return evidence


def run(spark: Any, *, catalog: str, schema: str, volume: str, run_scope: str) -> dict[str, Any]:
    names = resource_names(run_scope)
    if schema != names["schema"] or volume != names["volume"]:
        raise ValueError("bundle resource names do not match the declared run scope")
    output = Path(f"/Volumes/{catalog}/{schema}/{volume}/{run_scope}")
    results: list[dict[str, Any]] = []

    for scenario_name in MANAGED_SCENARIOS:
        scenario = SCENARIO_ROOT / f"{scenario_name}.json"
        if scenario_name == "008_interrupted_publish":
            for fault in FAULTS:
                isolated_scope = f"{run_scope}-{fault.replace('_', '-')}"
                interrupted = run_managed_case(
                    spark,
                    scenario,
                    catalog=catalog,
                    schema=schema,
                    run_scope=isolated_scope,
                    fault_at=fault,
                )
                pointer_after_fault = DeltaStateStore(
                    spark, catalog, schema, isolated_scope
                ).load(scenario_name)
                retry = run_managed_case(
                    spark,
                    scenario,
                    catalog=catalog,
                    schema=schema,
                    run_scope=isolated_scope,
                )
                results.append(
                    {
                        "scenario": scenario_name,
                        "fault_at": fault,
                        "interrupted": interrupted.to_dict(),
                        "pointer_after_fault": {
                            "state_version": pointer_after_fault["state_version"],
                            "state_hash": pointer_after_fault["state_hash"],
                        },
                        "retry": retry.to_dict(),
                    }
                )
            normal_scope = f"{run_scope}-uninterrupted"
        else:
            normal_scope = run_scope
        result = run_managed_case(
            spark,
            scenario,
            catalog=catalog,
            schema=schema,
            run_scope=normal_scope,
        )
        _write_json(output / "results" / f"{scenario_name}.json", result.to_dict())
        results.append({"scenario": scenario_name, "result": result.to_dict()})

    gate = validate_managed_scenario_results(results)
    report = {
        "result": "PASS",
        "run_scope": run_scope,
        "scenario_count": len(MANAGED_SCENARIOS),
        "fault_hooks": list(FAULTS),
        "oracle_gate": gate,
        "results": results,
        "delta_history": _history(spark, DeltaStateStore(spark, catalog, schema, run_scope)),
    }
    redacted = redact_evidence(report)
    _write_json(output / "managed-proof.json", redacted)
    return redacted


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--volume", required=True)
    parser.add_argument("--run-scope", required=True)
    args = parser.parse_args()
    from pyspark.sql import SparkSession

    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()
    report = run(
        spark,
        catalog=args.catalog,
        schema=args.schema,
        volume=args.volume,
        run_scope=args.run_scope,
    )
    print(json.dumps(report, sort_keys=True))
    if report["result"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
