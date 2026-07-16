"""Build deterministic, licence-bounded reliability-reference release assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

T2_COMMIT = "45125f1e064f28ce03ef7e0f15acceb18c34604f"
ALLOWED_ROOTS = ("benchmark/reliability_reference/", "docs/reliability-reference/")


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
        for path in paths:
            payload = _blob(repo, ref, path)
            info = zipfile.ZipInfo(path, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            pack.writestr(info, payload)
            file_entries.append(
                {
                    "fileName": path,
                    "checksums": [
                        {"algorithm": "SHA256", "checksumValue": hashlib.sha256(payload).hexdigest()}
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
    build_release(repo, target, args.version, args.managed_result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
