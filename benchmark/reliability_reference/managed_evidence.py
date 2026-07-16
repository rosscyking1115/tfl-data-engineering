"""Safety helpers for bounded managed-proof evidence and release manifests."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


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
