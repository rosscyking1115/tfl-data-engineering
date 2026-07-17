"""Drop only the uniquely scoped T3 Delta tables before bundle destruction."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    starts = [Path.cwd().resolve()]
    script_file = globals().get("__file__")
    if script_file:
        starts.insert(0, Path(str(script_file)).resolve())
    for start in starts:
        for parent in (start, *start.parents):
            if (parent / "benchmark" / "reliability_reference").is_dir():
                return parent
    raise RuntimeError("synced reliability-reference package is unavailable")


REPO_ROOT = _repo_root()
sys.path.insert(0, str(REPO_ROOT))

from benchmark.reliability_reference.delta_runner import DeltaStateStore  # noqa: E402
from benchmark.reliability_reference.managed_evidence import resource_names  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--run-scope", required=True)
    args = parser.parse_args()
    expected = resource_names(args.run_scope)
    if args.schema != expected["schema"]:
        raise ValueError("cleanup schema does not match the declared run scope")

    from pyspark.sql import SparkSession

    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()
    store = DeltaStateStore(spark, args.catalog, args.schema, args.run_scope)
    statements = store.cleanup_statements()
    for statement in statements:
        spark.sql(statement)
    print(json.dumps({"result": "PASS", "dropped_table_count": len(statements)}))


if __name__ == "__main__":
    main()
