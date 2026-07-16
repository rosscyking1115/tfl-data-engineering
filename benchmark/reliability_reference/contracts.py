"""Contract, fixture, and workspace validation."""

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .constants import (
    CONTRACT_ROOT,
    EXPECTED_ROOT,
    FIXTURE_ROOT,
    GATE0_FIXTURE_ROOT,
    SCHEMA_MAP_PATH,
)


class ContractError(ValueError):
    """A committed or caller-provided contract is invalid."""


class ObjectValidationError(ValueError):
    """A source object cannot be accepted atomically."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"invalid JSON contract {path}: {error}") from error


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def header_variant_id(headers: list[str]) -> str:
    encoded = json.dumps(headers, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def read_headers(path: Path) -> list[str]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return next(csv.reader(handle))
    except (OSError, StopIteration, csv.Error) as error:
        raise ObjectValidationError("malformed_csv", f"cannot read CSV header: {error}") from error


def schema_map() -> dict[str, Any]:
    return load_json(SCHEMA_MAP_PATH)


def find_variant(headers: list[str]) -> dict[str, Any]:
    variants = schema_map()["variants"]
    for variant in variants:
        if variant["headers"] == headers:
            return variant
    known = {header for variant in variants for header in variant["headers"]}
    code = "unknown_header" if any(header not in known for header in headers) else "missing_header"
    raise ObjectValidationError(code, f"unverified ordered header: {headers!r}")


def validate_workspace(workspace: Path) -> Path:
    resolved = workspace.resolve()
    protected = (FIXTURE_ROOT.resolve(), EXPECTED_ROOT.resolve(), CONTRACT_ROOT.resolve())
    if any(resolved == root or resolved.is_relative_to(root) for root in protected):
        raise ContractError("workspace cannot be inside committed benchmark assets")
    return resolved


def load_sidecar(sidecar_name: str) -> tuple[dict[str, Any], Path]:
    sidecar_path = FIXTURE_ROOT / sidecar_name
    metadata = load_json(sidecar_path)
    required = {
        "object_id",
        "file",
        "fixture_kind",
        "evidence_basis",
        "content_sha256",
        "header_variant_id",
        "ownership_period",
        "expected_source_rows",
        "supersedes_object_id",
        "publication_decision",
        "expected_disposition",
    }
    missing = sorted(required - metadata.keys())
    if missing:
        raise ContractError(f"{sidecar_name}: missing sidecar fields {missing}")
    fixture = FIXTURE_ROOT / metadata["file"]
    if not fixture.is_file():
        raise ContractError(f"{sidecar_name}: fixture does not exist: {fixture.name}")
    actual_hash = file_sha256(fixture)
    if actual_hash != metadata["content_sha256"]:
        raise ContractError(
            f"{sidecar_name}: content hash {actual_hash} != {metadata['content_sha256']}"
        )
    actual_header = header_variant_id(read_headers(fixture))
    if actual_header != metadata["header_variant_id"]:
        raise ContractError(
            f"{sidecar_name}: header fingerprint {actual_header} != {metadata['header_variant_id']}"
        )
    if metadata["fixture_kind"] != "constructed":
        raise ContractError(f"{sidecar_name}: only constructed fixtures are authorized")
    if metadata["publication_decision"] != "publish_constructed":
        raise ContractError(f"{sidecar_name}: raw publication is not authorized")
    return metadata, fixture


def validate_fixture_pack() -> dict[str, Any]:
    migrated = []
    decisions = Counter()
    for sidecar_path in sorted(FIXTURE_ROOT.glob("*.sidecar.json")):
        metadata, fixture = load_sidecar(sidecar_path.name)
        decisions[metadata["publication_decision"]] += 1
        origin_name = metadata.get("origin_gate0_file")
        if origin_name:
            origin = GATE0_FIXTURE_ROOT / origin_name
            if not origin.is_file() or origin.read_bytes() != fixture.read_bytes():
                raise ContractError(f"{fixture.name}: bytes differ from frozen Gate 0 fixture")
            if metadata.get("origin_gate0_sha256") != file_sha256(origin):
                raise ContractError(f"{fixture.name}: frozen Gate 0 digest differs")
            migrated.append(fixture.name)
    return {
        "fixture_count": len(migrated),
        "total_fixture_count": len(list(FIXTURE_ROOT.glob("*.sidecar.json"))),
        "gate0_byte_matches": len(migrated),
        "publication_decisions": dict(decisions),
        "schema_files": sorted(path.name for path in CONTRACT_ROOT.glob("*.schema.json")),
    }
