"""Assertions against the committed, human-readable semantic oracle."""

from pathlib import Path
from typing import Any, Mapping

from .canonical import state_hash
from .contracts import ContractError, load_json

EXPECTED_ROOT = Path(__file__).parent / "expected"
ORACLE_INDEX = EXPECTED_ROOT / "oracle-index.json"


def validate_oracle(scenario_names: set[str]) -> dict[str, int]:
    """Verify every executable scenario has an intact canonical state oracle."""
    index = load_json(ORACLE_INDEX)
    actual_names = set(index.get("scenarios", {}))
    if actual_names != scenario_names:
        missing = sorted(scenario_names - actual_names)
        extra = sorted(actual_names - scenario_names)
        raise ContractError(f"oracle scenario mismatch; missing={missing}, extra={extra}")
    state_refs = set()
    for scenario_name, expected in index["scenarios"].items():
        state_ref = expected["state_ref"]
        state_refs.add(state_ref)
        rows = load_json(EXPECTED_ROOT / state_ref)
        if state_hash(rows) != expected["state_hash"]:
            raise ContractError(f"{scenario_name}: committed oracle state hash is invalid")
    return {
        "oracle_scenario_count": len(actual_names),
        "oracle_state_count": len(state_refs),
    }


def assert_expected(result: Mapping[str, Any], scenario_name: str) -> None:
    """Raise a precise contract error when a result diverges from the oracle."""
    index = load_json(ORACLE_INDEX)
    try:
        expected = index["scenarios"][scenario_name]
    except KeyError as error:
        raise ContractError(f"{scenario_name}: no committed oracle") from error

    expected_rows = load_json(EXPECTED_ROOT / expected["state_ref"])
    if result.get("terminal_status") != "success":
        raise ContractError(f"{scenario_name}: terminal status is not success")
    if result.get("state_hash") != expected["state_hash"]:
        raise ContractError(f"{scenario_name}: state hash differs from oracle")
    if result.get("canonical_rows") != expected_rows:
        raise ContractError(f"{scenario_name}: canonical rows differ from oracle")

    actual_events = [
        [item["object_id"], item["disposition"], item["reason_code"]]
        for item in result.get("reconciliation", [])
    ]
    if actual_events != expected["events"]:
        raise ContractError(f"{scenario_name}: reconciliation differs from oracle")

    actual_history = [
        [item["object_id"], item["disposition"]]
        for item in result.get("object_history", [])
    ]
    expected_history = [[object_id, disposition] for object_id, disposition, _ in expected["events"]]
    if actual_history != expected_history:
        raise ContractError(f"{scenario_name}: object history differs from oracle")
