"""Build deterministic, licence-bounded reliability-reference release assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

T2_COMMIT = "45125f1e064f28ce03ef7e0f15acceb18c34604f"
ALLOWED_ROOTS = ("benchmark/reliability_reference/", "docs/reliability-reference/")
DELTA_TABLES = ("staging", "states", "manifests", "current_pointer", "run_events")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_WORKSPACE = re.compile(r"https://[^\s\"']+\.cloud\.databricks\.com", re.IGNORECASE)
_TOKEN = re.compile(r"\bdapi[a-z0-9]{20,}\b", re.IGNORECASE)
_IDENTITY_KEYS = {"email", "host", "profile", "token", "user", "username", "workspace_url"}
MANAGED_SCENARIOS = (
    "001_initial_variants",
    "002_duplicate_replay",
    "003_new_period",
    "004_corrected_period",
    "008_interrupted_publish",
    "009_full_rebuild",
    "011_incompatible_replacement",
)


def redact_evidence(value: Any) -> Any:
    """Remove workspace identity and token-shaped values from release evidence."""
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
        rendered = _WORKSPACE.sub("<redacted>", value)
        rendered = _EMAIL.sub("<redacted>", rendered)
        return _TOKEN.sub("<redacted>", rendered)
    return value


class ReleaseError(ValueError):
    """The requested release would violate the accepted release policy."""


def validate_release_policy(version: str, result: str, target_commit: str) -> None:
    if result == "STOP":
        raise ReleaseError("STOP blocks every release")
    if version == "0.3.0" and result != "PASS":
        raise ReleaseError("version 0.3.0 requires a managed PASS")
    if version == "0.2.0":
        if result not in {"NARROW", "FAIL"}:
            raise ReleaseError("version 0.2.0 fallback requires NARROW or FAIL")
        if target_commit != T2_COMMIT:
            raise ReleaseError(f"version 0.2.0 must target the frozen T2 commit {T2_COMMIT}")
    elif version != "0.3.0":
        raise ReleaseError(f"unsupported release version: {version}")


def validate_managed_release_evidence(evidence: dict[str, Any]) -> None:
    if evidence.get("result") != "PASS":
        raise ReleaseError("version 0.3.0 requires committed managed PASS evidence")
    required = {
        "baseline_commit",
        "candidate_commit",
        "managed_attempts",
        "reason_code",
        "bundle_hash",
        "fixture_manifest_hash",
        "claim_ledger_hash",
        "candidate_tree_hash",
        "first_deployment_utc",
        "deadline_utc",
        "scenario_results",
        "portable_comparison",
        "delta_history",
        "resource_inventory_before",
        "resource_inventory_after",
        "teardown",
    }
    missing = sorted(required - evidence.keys())
    if missing:
        raise ReleaseError(f"managed PASS evidence is missing fields: {missing}")
    if evidence["baseline_commit"] != T2_COMMIT:
        raise ReleaseError("managed PASS evidence has the wrong T2 baseline commit")
    if not _COMMIT.fullmatch(str(evidence["candidate_commit"])):
        raise ReleaseError("managed PASS evidence requires a full candidate commit")
    if evidence["managed_attempts"] not in {1, 2}:
        raise ReleaseError("managed PASS evidence exceeds the bounded attempt count")
    if evidence["reason_code"] != "managed_conformance_pass":
        raise ReleaseError("managed PASS evidence has the wrong reason code")
    for field in (
        "bundle_hash",
        "fixture_manifest_hash",
        "claim_ledger_hash",
        "candidate_tree_hash",
    ):
        if not _SHA256.fullmatch(str(evidence[field])):
            raise ReleaseError(f"managed PASS evidence requires a SHA-256 {field}")
    try:
        started = datetime.fromisoformat(str(evidence["first_deployment_utc"]).replace("Z", "+00:00"))
        deadline = datetime.fromisoformat(str(evidence["deadline_utc"]).replace("Z", "+00:00"))
    except ValueError as error:
        raise ReleaseError("managed PASS evidence has invalid UTC bounds") from error
    duration = (deadline - started).total_seconds()
    if started.utcoffset() != timezone.utc.utcoffset(started) or not 0 < duration <= 7200:
        raise ReleaseError("managed PASS evidence exceeds the two-hour UTC window")

    scenario_results = evidence["scenario_results"]
    if not isinstance(scenario_results, list):
        raise ReleaseError("managed scenario completeness is not a list")
    if not all(isinstance(item, dict) for item in scenario_results):
        raise ReleaseError("managed scenario completeness contains invalid entries")
    scenario_names = [item.get("case_id") for item in scenario_results]
    if scenario_names != list(MANAGED_SCENARIOS) or not all(
        item.get("result") == "PASS" for item in scenario_results
    ):
        raise ReleaseError("managed scenario completeness does not match the bounded case set")
    comparison = evidence["portable_comparison"]
    if not isinstance(comparison, dict):
        raise ReleaseError("managed PASS evidence lacks portable comparison")
    comparison_scenarios = comparison.get("scenarios", [])
    if not isinstance(comparison_scenarios, list) or not all(
        isinstance(item, dict) for item in comparison_scenarios
    ):
        raise ReleaseError("managed PASS evidence has invalid portable comparison entries")
    if comparison.get("result") != "PASS" or [
        item.get("case_id") for item in comparison_scenarios
    ] != list(MANAGED_SCENARIOS) or not all(
        item.get("result") == "PASS" for item in comparison_scenarios
    ):
        raise ReleaseError("managed PASS evidence lacks complete portable comparison")
    history = evidence["delta_history"]
    if not isinstance(history, dict) or any(not history.get(table) for table in DELTA_TABLES):
        raise ReleaseError("managed PASS evidence lacks Delta history for every owned table")
    if not isinstance(evidence["resource_inventory_before"], list) or not isinstance(
        evidence["resource_inventory_after"], list
    ):
        raise ReleaseError("managed PASS evidence requires resource inventories")
    if redact_evidence(evidence) != evidence:
        raise ReleaseError("managed PASS evidence contains unredacted identity or credentials")

    teardown = evidence.get("teardown", {})
    required_absence = (
        "job_absent",
        "schema_absent",
        "volume_absent",
        "tables_absent",
        "bundle_artifacts_absent",
    )
    if not teardown.get("required") or not teardown.get("verified"):
        raise ReleaseError("managed PASS evidence requires verified teardown")
    if not all(teardown.get(field) is True for field in required_absence):
        raise ReleaseError("managed PASS evidence requires complete resource absence checks")


def _git(repo: Path, *arguments: str, text: bool = False) -> str | bytes:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=True,
        capture_output=True,
        text=text,
    )
    return completed.stdout


def _release_paths(repo: Path, ref: str) -> list[str]:
    rendered = _git(
        repo,
        "ls-tree",
        "-r",
        "--name-only",
        ref,
        "--",
        "benchmark/reliability_reference",
        "docs/reliability-reference",
        text=True,
    )
    paths = [line.strip() for line in str(rendered).splitlines() if line.strip()]
    for path in paths:
        normalized = PurePosixPath(path).as_posix()
        if not normalized.startswith(ALLOWED_ROOTS):
            raise ReleaseError(f"release path is outside the allowlist: {path}")
        if normalized.startswith("app/") or PurePosixPath(normalized).name.startswith("live_"):
            raise ReleaseError(f"live application state is forbidden: {path}")
    return paths


def _blob(repo: Path, ref: str, path: str) -> bytes:
    value = _git(repo, "show", f"{ref}:{path}")
    return bytes(value)


def _tree_manifest_hash(repo: Path, ref: str, *roots: str) -> str:
    rendered = _git(
        repo,
        "ls-tree",
        "-r",
        "--name-only",
        ref,
        "--",
        *roots,
        text=True,
    )
    entries = [
        {"path": path, "sha256": hashlib.sha256(_blob(repo, ref, path)).hexdigest()}
        for path in sorted(line.strip() for line in str(rendered).splitlines() if line.strip())
    ]
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _fixture_manifest_hash(repo: Path, ref: str) -> str:
    return _tree_manifest_hash(repo, ref, "benchmark/reliability_reference/fixtures")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_release(
    repo: Path,
    ref: str,
    version: str,
    result: str,
    output: Path,
) -> dict[str, Path]:
    """Materialize release assets from a Git tree without checking it out."""

    repo = repo.resolve()
    output.mkdir(parents=True, exist_ok=True)
    commit = str(_git(repo, "rev-parse", f"{ref}^{{commit}}", text=True)).strip()
    paths = _release_paths(repo, ref)
    if not paths:
        raise ReleaseError("release tree contains no reliability-reference files")

    archive = output / f"reliability-reference-v{version}.zip"
    file_entries: list[dict[str, Any]] = []
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as pack:
        for index, path in enumerate(paths, start=1):
            payload = _blob(repo, ref, path)
            payload_hash = hashlib.sha256(payload).hexdigest()
            info = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            pack.writestr(info, payload)
            file_entries.append(
                {
                    "SPDXID": f"SPDXRef-File-{index}-{payload_hash[:12]}",
                    "fileName": path,
                    "licenseConcluded": "NOASSERTION",
                    "licenseInfoInFiles": ["NOASSERTION"],
                    "copyrightText": "NOASSERTION",
                    "checksums": [
                        {"algorithm": "SHA256", "checksumValue": payload_hash}
                    ],
                }
            )

    created_raw = str(_git(repo, "show", "-s", "--format=%cI", commit, text=True)).strip()
    created = (
        datetime.fromisoformat(created_raw)
        .astimezone(timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    namespace_digest = hashlib.sha256(f"{commit}:{version}".encode()).hexdigest()
    sbom = output / f"reliability-reference-v{version}.spdx.json"
    sbom.write_text(
        json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "dataLicense": "CC0-1.0",
                "SPDXID": "SPDXRef-DOCUMENT",
                "name": f"tfl-reliability-reference-v{version}",
                "documentNamespace": f"https://github.com/rosscyking1115/tfl-data-engineering/spdx/{namespace_digest}",
                "creationInfo": {
                    "created": created,
                    "creators": ["Tool: build_reliability_release.py"],
                },
                "files": file_entries,
                "relationships": [
                    {
                        "spdxElementId": "SPDXRef-DOCUMENT",
                        "relationshipType": "DESCRIBES",
                        "relatedSpdxElement": item["SPDXID"],
                    }
                    for item in file_entries
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = output / "release-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "version": version,
                "managed_result": result,
                "target_commit": commit,
                "source_file_count": len(paths),
                "archive_sha256": _sha256(archive),
                "sbom_sha256": _sha256(sbom),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    notes = output / "RELEASE_NOTES.md"
    notes.write_text(
        f"# Reliability reference v{version}\n\n"
        "Constructed, licence-bounded fixtures and reviewed semantic outputs only. "
        "This is not raw TfL data, production Databricks operation, a performance result, "
        "or an SLA claim. See the included attribution and limitations.\n",
        encoding="utf-8",
    )
    checksums = output / "SHA256SUMS"
    checksum_files = (archive, sbom, manifest, notes)
    checksums.write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in checksum_files),
        encoding="utf-8",
    )
    return {
        "archive": archive,
        "sbom": sbom,
        "manifest": manifest,
        "notes": notes,
        "checksums": checksums,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, choices=("0.2.0", "0.3.0"))
    parser.add_argument("--managed-result", required=True, choices=("PASS", "NARROW", "FAIL", "STOP"))
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    target = str(_git(repo, "rev-parse", f"{args.target}^{{commit}}", text=True)).strip()
    validate_release_policy(args.version, args.managed_result, target)
    if args.version == "0.3.0":
        evidence = json.loads(
            _blob(
                repo,
                target,
                "docs/reliability-reference/releases/0.3.0/managed-proof.json",
            )
        )
        validate_managed_release_evidence(evidence)
        expected_hashes = {
            "bundle_hash": hashlib.sha256(
                _blob(repo, target, "infra/databricks/reliability_reference/databricks.yml")
            ).hexdigest(),
            "fixture_manifest_hash": _fixture_manifest_hash(repo, target),
            "claim_ledger_hash": hashlib.sha256(
                _blob(
                    repo,
                    target,
                    "docs/reliability-reference/releases/0.3.0/claim-ledger.json",
                )
            ).hexdigest(),
            "candidate_tree_hash": _tree_manifest_hash(
                repo,
                target,
                "benchmark/reliability_reference",
                "infra/databricks/reliability_reference",
            ),
        }
        for field, expected in expected_hashes.items():
            if evidence[field] != expected:
                raise ReleaseError(f"managed evidence {field} does not match the release tree")
    build_release(repo, target, args.version, args.managed_result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
