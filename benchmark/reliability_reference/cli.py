"""Reviewer-facing command surface for validation, execution, and comparison."""

import argparse
import json
from pathlib import Path
from typing import Any

from .compare import compare_results
from .constants import CONTRACT_VERSION, SCENARIO_ROOT, VERSION
from .contracts import ContractError, load_json, validate_fixture_pack
from .oracle import assert_expected, validate_oracle
from .runner import run_case


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _executable_scenarios() -> list[Path]:
    return sorted(path for path in SCENARIO_ROOT.glob("*.json") if not path.name.startswith("010_"))


def validate() -> dict[str, Any]:
    fixture_report = validate_fixture_pack()
    scenarios = _executable_scenarios()
    for path in scenarios:
        scenario = load_json(path)
        if scenario.get("contract_version") != CONTRACT_VERSION:
            raise ContractError(f"{path.name}: unsupported contract version")
        if not scenario.get("operations"):
            raise ContractError(f"{path.name}: no operations")
    return {
        "result": "PASS",
        "benchmark_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "scenario_count": len(scenarios),
        **validate_oracle({path.stem for path in scenarios}),
        **fixture_report,
    }


def run(engine: str, scenario_selection: str, output: Path) -> dict[str, Any]:
    available = {path.stem: path for path in _executable_scenarios()}
    if scenario_selection == "all":
        selected = list(available.items())
    else:
        match = next(
            ((name, path) for name, path in available.items() if name == scenario_selection),
            None,
        )
        if match is None:
            raise ContractError(f"unknown scenario: {scenario_selection}")
        selected = [match]
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for name, scenario_path in selected:
        result = run_case(engine, scenario_path, workspace=output / "workspaces" / name)
        rendered = result.to_dict()
        assert_expected(rendered, name)
        _write_json(output / "results" / f"{name}.json", rendered)
        summaries.append(
            {
                "case_id": result.case_id,
                "terminal_status": result.terminal_status,
                "state_hash": result.state_hash,
                "canonical_rows": len(result.canonical_rows),
            }
        )
    passed = all(item["terminal_status"] == "success" for item in summaries)
    report = {
        "result": "PASS" if passed else "FAIL",
        "benchmark_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "engine": engine,
        "scenarios": summaries,
    }
    _write_json(output / "conformance.json", report)
    lines = [
        f"# {engine.title()} conformance",
        "",
        f"Result: **{report['result']}**",
        "",
        "| Scenario | Status | Rows | State hash |",
        "|---|---:|---:|---|",
    ]
    lines.extend(
        f"| {item['case_id']} | {item['terminal_status']} | {item['canonical_rows']} | `{item['state_hash']}` |"
        for item in summaries
    )
    (output / "conformance.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def compare(duckdb_output: Path, spark_output: Path, output: Path) -> dict[str, Any]:
    duckdb_results = {path.name: path for path in (duckdb_output / "results").glob("*.json")}
    spark_results = {path.name: path for path in (spark_output / "results").glob("*.json")}
    names = sorted(duckdb_results.keys() | spark_results.keys())
    scenarios = []
    for name in names:
        if name not in duckdb_results or name not in spark_results:
            scenarios.append(
                {
                    "case_id": Path(name).stem,
                    "result": "FAIL",
                    "missing_engine_result": "duckdb" if name not in duckdb_results else "spark",
                }
            )
            continue
        expected = load_json(duckdb_results[name])
        actual = load_json(spark_results[name])
        scenarios.append({"case_id": expected["case_id"], **compare_results(expected, actual)})
    passed = bool(scenarios) and all(item["result"] == "PASS" for item in scenarios)
    report = {
        "result": "PASS" if passed else "FAIL",
        "benchmark_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "comparison": "decoded canonical rows, reconciliation, object history, and state hash",
        "scenarios": scenarios,
    }
    _write_json(output / "comparison.json", report)
    lines = [
        "# DuckDB/Spark semantic comparison",
        "",
        f"Result: **{report['result']}**",
        "",
        "| Scenario | Result |",
        "|---|---:|",
    ]
    lines.extend(f"| {item['case_id']} | {item['result']} |" for item in scenarios)
    output.mkdir(parents=True, exist_ok=True)
    (output / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def compare_managed(reference_output: Path, managed_output: Path, output: Path) -> dict[str, Any]:
    """Compare exported Delta semantics with the authoritative portable output."""
    reference_results = {
        path.name: path for path in (reference_output / "results").glob("*.json")
    }
    managed_results = {path.name: path for path in (managed_output / "results").glob("*.json")}
    scenarios = []
    for name, managed_path in sorted(managed_results.items()):
        if name not in reference_results:
            scenarios.append(
                {
                    "case_id": Path(name).stem,
                    "result": "FAIL",
                    "missing_engine_result": "duckdb",
                }
            )
            continue
        expected = load_json(reference_results[name])
        actual = load_json(managed_path)
        scenarios.append({"case_id": expected["case_id"], **compare_results(expected, actual)})
    passed = bool(scenarios) and all(item["result"] == "PASS" for item in scenarios)
    report = {
        "result": "PASS" if passed else "FAIL",
        "benchmark_version": VERSION,
        "contract_version": CONTRACT_VERSION,
        "comparison": "portable DuckDB oracle versus managed Delta decoded semantics",
        "reference_engine": "duckdb",
        "managed_engine": "delta",
        "scenarios": scenarios,
    }
    _write_json(output / "comparison.json", report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tfl-reliability")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate")
    commands.add_parser("version")
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--engine", choices=("duckdb", "spark"), required=True)
    run_parser.add_argument("--scenario", default="all")
    run_parser.add_argument("--output", type=Path, required=True)
    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("--duckdb", type=Path, required=True)
    compare_parser.add_argument("--spark", type=Path, required=True)
    compare_parser.add_argument("--output", type=Path, required=True)
    managed_parser = commands.add_parser("compare-managed")
    managed_parser.add_argument("--reference", type=Path, required=True)
    managed_parser.add_argument("--managed", type=Path, required=True)
    managed_parser.add_argument("--output", type=Path, required=True)
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        if args.command == "validate":
            print(json.dumps(validate(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "version":
            print(VERSION)
            return 0
        if args.command == "run":
            report = run(args.engine, args.scenario, args.output)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["result"] == "PASS" else 1
        if args.command == "compare-managed":
            report = compare_managed(args.reference, args.managed, args.output)
        else:
            report = compare(args.duckdb, args.spark, args.output)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["result"] == "PASS" else 1
    except ContractError as error:
        parser_error = {"result": "FAIL", "error": str(error)}
        print(json.dumps(parser_error, ensure_ascii=False))
        return 2
