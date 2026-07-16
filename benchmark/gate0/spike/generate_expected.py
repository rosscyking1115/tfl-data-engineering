"""Regenerate reviewed DuckDB expected outputs for every committed Gate 0 case."""

import json

from .runner import GATE0_ROOT, run_case

CASE_NAMES = (
    "normalize-five-variants",
    "duplicate-replay",
    "correction-replaces-period",
    "incompatible-preserves-state",
    "dst-ambiguity-rejected",
)


def main() -> None:
    output_dir = GATE0_ROOT / "expected"
    output_dir.mkdir(parents=True, exist_ok=True)
    for case_name in CASE_NAMES:
        result = run_case("duckdb", GATE0_ROOT / "cases" / f"{case_name}.json")
        destination = output_dir / f"{case_name}.json"
        destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"{case_name}: {result['state_hash']} -> {destination}")


if __name__ == "__main__":
    main()
