"""Safety helpers for bounded managed-proof evidence and release manifests."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from .constants import MANAGED_SCENARIOS
from .contracts import ContractError
from .oracle import assert_expected


class EvidenceError(ValueError):
    """Managed evidence is unsafe or does not satisfy the release gate."""


_SAFE_SCOPE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_WORKSPACE = re.compile(r"https://[^\s\"']+\.cloud\.databricks\.com", re.IGNORECASE)
_TOKEN = re.compile(r"\bdapi[a-z0-9]{20,}\b", re.IGNORECASE)
_IDENTITY_KEYS = {
    "email",
    "host",
    "operator_email",
    "profile",
    "token",
    "user",
    "username",
    "workspace_url",
}


def resource_names(run_scope: str) -> dict[str, str]:
    """Return deterministic, isolated resource names for one managed attempt."""
    if not _SAFE_SCOPE.fullmatch(run_scope):
        raise EvidenceError("run scope must contain lowercase letters, digits, and single hyphens")
    return {
        "schema": f"tfl_reliability_t3_{run_scope.replace('-', '_')}",
        "volume": "evidence",
        "job": f"tfl-reliability-t3-{run_scope}",
    }


def _redact_string(value: str) -> str:
    rendered = _WORKSPACE.sub("<redacted>", value)
    rendered = _EMAIL.sub("<redacted>", rendered)
    return _TOKEN.sub("<redacted>", rendered)


def redact_evidence(value: Any) -> Any:
    """Recursively remove workspace identity and token-shaped values."""
    if isinstance(value, Mapping):
        return {
            str(key): "<redacted>"
            if str(key).lower() in _IDENTITY_KEYS
            else redact_evidence(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_evidence(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def validate_managed_evidence(evidence: Mapping[str, Any]) -> None:
    """Validate the terminal decision and mandatory teardown invariant."""
    required = {
        "result",
        "baseline_commit",
        "candidate_commit",
        "managed_attempts",
        "reason_code",
        "teardown",
        "scenario_results",
    }
    missing = sorted(required - evidence.keys())
    if missing:
        raise EvidenceError(f"managed evidence missing fields: {missing}")
    if evidence["result"] not in {"PASS", "NARROW", "FAIL", "STOP"}:
        raise EvidenceError("managed evidence has invalid terminal result")
    teardown = evidence["teardown"]
    if not isinstance(teardown, Mapping) or not teardown.get("verified"):
        raise EvidenceError("teardown must be independently verified")
    if evidence["result"] == "PASS" and not teardown.get("required"):
        raise EvidenceError("PASS requires a managed teardown")


def validate_managed_scenario_results(results: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Require complete oracle parity and all recovery invariants before managed PASS."""

    normal = [item for item in results if "result" in item]
    normal_names = [str(item.get("scenario")) for item in normal]
    if len(normal_names) != len(set(normal_names)) or set(normal_names) != set(MANAGED_SCENARIOS):
        raise EvidenceError("managed scenario completeness differs from the bounded case set")
    by_name = {str(item["scenario"]): item["result"] for item in normal}
    for scenario_name in MANAGED_SCENARIOS:
        result = by_name[scenario_name]
        if not isinstance(result, Mapping) or result.get("terminal_status") != "success":
            raise EvidenceError(f"{scenario_name}: managed terminal status is not success")
        try:
            assert_expected(dict(result), scenario_name)
        except ContractError as error:
            raise EvidenceError(f"{scenario_name}: managed result differs from oracle: {error}") from error

    faults = [item for item in results if "fault_at" in item]
    expected_faults = {"after_stage", "after_validation", "before_pointer_swap"}
    actual_faults = {str(item.get("fault_at")) for item in faults}
    if len(faults) != len(expected_faults) or actual_faults != expected_faults:
        raise EvidenceError("managed fault-hook completeness differs from the contract")
    clean = by_name["009_full_rebuild"]
    uninterrupted = by_name["008_interrupted_publish"]
    if (
        uninterrupted["state_hash"] != clean["state_hash"]
        or uninterrupted["canonical_rows"] != clean["canonical_rows"]
    ):
        raise EvidenceError("uninterrupted execution differs from the clean rebuild")
    for item in faults:
        interrupted = item.get("interrupted", {})
        pointer = item.get("pointer_after_fault", {})
        retry = item.get("retry", {})
        if interrupted.get("terminal_status") != "interrupted":
            raise EvidenceError(f"{item.get('fault_at')}: fault did not interrupt")
        if pointer.get("state_hash") != interrupted.get("state_hash"):
            raise EvidenceError(f"{item.get('fault_at')}: pointer changed after interruption")
        if retry.get("terminal_status") != "success":
            raise EvidenceError(f"{item.get('fault_at')}: retry did not succeed")
        if retry.get("state_hash") != clean["state_hash"] or retry.get("canonical_rows") != clean[
            "canonical_rows"
        ]:
            raise EvidenceError(f"{item.get('fault_at')}: retry differs from clean rebuild")
    return {
        "scenario_count": len(normal),
        "fault_hook_count": len(faults),
        "oracle_result": "PASS",
    }


def build_release_manifest(root: Path, files: Iterable[Path]) -> list[dict[str, Any]]:
    """Hash release inputs while refusing live application snapshots."""
    root = root.resolve()
    manifest = []
    for path in sorted((Path(item).resolve() for item in files), key=lambda item: item.as_posix()):
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError as error:
            raise EvidenceError(f"release file is outside repository root: {path}") from error
        if relative.startswith("app/gold_export/live_") or (
            relative.startswith("app/gold_export/") and Path(relative).name.startswith("live_")
        ):
            raise EvidenceError("live snapshot files are forbidden from release evidence")
        payload = path.read_bytes()
        manifest.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        )
    return manifest
