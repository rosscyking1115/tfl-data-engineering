import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from benchmark.reliability_reference.canonical import ordered_rows, state_hash
from benchmark.reliability_reference.constants import EMPTY_STATE_HASH, MANAGED_SCENARIOS
from benchmark.reliability_reference.delta_runner import (
    DeltaStateStore,
    DeltaTableNames,
    _execute_managed_case,
)
from benchmark.reliability_reference.duckdb_adapter import normalize_object
from benchmark.reliability_reference.managed_evidence import (
    EvidenceError,
    build_release_manifest,
    redact_evidence,
    resource_names,
    validate_managed_evidence,
    validate_managed_scenario_results,
)
from scripts.build_reliability_release import (
    T2_COMMIT,
    ReleaseError,
    _blob,
    _fixture_manifest_hash,
    _tree_manifest_hash,
    build_release,
    validate_managed_release_evidence,
    validate_release_policy,
)

ROOT = Path(__file__).parents[1]
SCENARIOS = ROOT / "benchmark" / "reliability_reference" / "scenarios"
RELEASE_DOCS = ROOT / "docs" / "reliability-reference" / "releases" / "0.3.0"


class MemoryManagedStore:
    def __init__(self):
        self.current: dict[str, dict[str, Any]] = {}
        self.prepared: dict[tuple[str, str], dict[str, Any]] = {}
        self.staged: list[dict[str, Any]] = []
        self.runs: list[dict[str, Any]] = []

    def load(self, case_id: str) -> dict[str, Any]:
        return self.current.get(
            case_id,
            {
                "state_version": None,
                "state_hash": EMPTY_STATE_HASH,
                "canonical_rows": [],
                "applied_hashes": [],
                "active_objects": {},
            },
        )

    def stage(
        self, run_id: str, case_id: str, candidate: dict[str, Any], operation: dict[str, Any]
    ) -> None:
        self.staged.append(
            {"run_id": run_id, "case_id": case_id, "candidate": candidate, "operation": operation}
        )

    def prepare_state(self, case_id: str, candidate: dict[str, Any]) -> str:
        rows = ordered_rows(candidate["canonical_rows"])
        digest = state_hash(rows)
        version = f"v-{digest.removeprefix('sha256:')[:16]}"
        self.prepared[(case_id, version)] = {
            **candidate,
            "state_version": version,
            "state_hash": digest,
            "canonical_rows": rows,
        }
        return version

    def commit_pointer(self, case_id: str, version: str) -> dict[str, Any]:
        state = self.prepared[(case_id, version)]
        self.current[case_id] = state
        return state

    def record_run(self, run_id: str, manifest: dict[str, Any]) -> str:
        self.runs.append({"run_id": run_id, **manifest})
        return f"runs/{run_id}.json"

    def artifact_references(self, manifest_ref: str) -> dict[str, str]:
        return {"current_pointer": "delta/current_pointer", "run_manifest": manifest_ref}


def test_resource_names_are_unique_and_reject_unsafe_scopes():
    names = resource_names("20260716-45125f1")

    assert names == {
        "schema": "tfl_reliability_t3_20260716_45125f1",
        "volume": "evidence",
        "job": "tfl-reliability-t3-20260716-45125f1",
    }
    for unsafe in ("", "*", "../default", "main.default", "DROP TABLE x"):
        with pytest.raises(EvidenceError, match="run scope"):
            resource_names(unsafe)


def test_evidence_redaction_removes_workspace_identity_and_tokens():
    evidence = {
        "workspace_url": "https://private.cloud.databricks.com",
        "operator_email": "person@example.com",
        "profile": "DEFAULT",
        "message": "run by person@example.com using "
        + "dapi"
        + "0123456789abcdef0123456789abcdef",
        "scenario_count": 7,
    }

    redacted = redact_evidence(evidence)
    rendered = json.dumps(redacted)

    assert "private.cloud.databricks.com" not in rendered
    assert "person@example.com" not in rendered
    assert "dapi" + "0123456789" not in rendered
    assert redacted["scenario_count"] == 7
    assert set(redacted.values()) >= {"<redacted>"}


def test_managed_evidence_requires_terminal_status_and_verified_teardown():
    valid = {
        "result": "NARROW",
        "baseline_commit": "45125f1e064f28ce03ef7e0f15acceb18c34604f",
        "candidate_commit": "working-tree",
        "managed_attempts": 0,
        "reason_code": "authentication_unavailable",
        "teardown": {"required": False, "verified": True},
        "scenario_results": [],
    }

    validate_managed_evidence(valid)

    with pytest.raises(EvidenceError, match="teardown"):
        validate_managed_evidence(
            {**valid, "result": "PASS", "teardown": {"required": True, "verified": False}}
        )


def test_release_manifest_is_relative_hashed_and_rejects_live_snapshots(tmp_path: Path):
    safe = tmp_path / "benchmark" / "contract.json"
    safe.parent.mkdir(parents=True)
    safe.write_text('{"contract": 1}\n', encoding="utf-8")

    manifest = build_release_manifest(tmp_path, [safe])

    assert manifest[0]["path"] == "benchmark/contract.json"
    assert len(manifest[0]["sha256"]) == 64
    assert manifest[0]["bytes"] == safe.stat().st_size

    live = tmp_path / "app" / "gold_export" / "live_bikepoint_daily.parquet"
    live.parent.mkdir(parents=True)
    live.write_bytes(b"forbidden")
    with pytest.raises(EvidenceError, match="live snapshot"):
        build_release_manifest(tmp_path, [live])


def test_bundle_is_serverless_scoped_and_never_syncs_application_state():
    bundle = ROOT / "infra" / "databricks" / "reliability_reference" / "databricks.yml"
    rendered = bundle.read_text(encoding="utf-8")

    assert "environment_key: default" in rendered
    assert "new_cluster:" not in rendered
    assert "existing_cluster_id:" not in rendered
    assert "app/gold_export" not in rendered
    assert "ingestion/" not in rendered
    assert "../../../benchmark/reliability_reference" in rendered
    assert "sync:\n  paths:" in rendered
    assert "  include:" not in rendered
    assert "tfl_reliability_t3_${var.run_suffix}" in rendered
    assert "mode: development" not in rendered
    assert "paths:" in rendered
    assert "--run-scope" in rendered


def test_delta_table_names_are_quoted_and_reject_identifier_injection():
    names = DeltaTableNames("workspace", "tfl_reliability_t3_20260716_45125f1")

    assert names.current_pointer == "`workspace`.`tfl_reliability_t3_20260716_45125f1`.`current_pointer`"
    assert names.states.endswith(".`states`")
    with pytest.raises(EvidenceError, match="identifier"):
        DeltaTableNames("workspace; DROP CATALOG main", "safe")


def test_managed_scenario_set_is_bounded_and_explicit():
    assert MANAGED_SCENARIOS == (
        "001_initial_variants",
        "002_duplicate_replay",
        "003_new_period",
        "004_corrected_period",
        "008_interrupted_publish",
        "009_full_rebuild",
        "011_incompatible_replacement",
    )


def test_cleanup_targets_only_the_five_uniquely_scoped_delta_tables():
    names = DeltaTableNames("workspace", "tfl_reliability_t3_20260716_45125f1")
    store = object.__new__(DeltaStateStore)
    store.names = names

    statements = store.cleanup_statements()

    assert len(statements) == 5
    assert statements == tuple(f"DROP TABLE IF EXISTS {table}" for table in names.all())
    assert all("DROP SCHEMA" not in statement for statement in statements)


def test_managed_job_contains_no_application_or_live_snapshot_paths():
    job = ROOT / "infra" / "databricks" / "reliability_reference" / "src" / "managed_job.py"
    cleanup = job.with_name("cleanup_job.py")
    adapter = ROOT / "benchmark" / "reliability_reference" / "delta_adapter.py"
    rendered = job.read_text(encoding="utf-8") + cleanup.read_text(encoding="utf-8")
    adapter_source = adapter.read_text(encoding="utf-8")

    assert "app/gold_export" not in rendered
    assert "live_" not in rendered
    assert "MANAGED_SCENARIOS" in rendered
    assert "cleanup_statements" in rendered
    assert "spark.createDataFrame" in adapter_source
    assert "spark.read" not in adapter_source


@pytest.mark.parametrize("script_name", ["managed_job.py", "cleanup_job.py"])
def test_managed_scripts_discover_synced_root_without_file_global(
    monkeypatch: pytest.MonkeyPatch, script_name: str
):
    script = ROOT / "infra" / "databricks" / "reliability_reference" / "src" / script_name
    spec = importlib.util.spec_from_file_location(f"test_{script.stem}", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.delattr(module, "__file__")
    monkeypatch.chdir(ROOT)

    assert module._repo_root() == ROOT


def test_release_policy_falls_back_to_exact_t2_commit_and_blocks_stop():
    validate_release_policy("0.2.0", "NARROW", T2_COMMIT)
    validate_release_policy("0.2.0", "FAIL", T2_COMMIT)

    with pytest.raises(ReleaseError, match="T2 commit"):
        validate_release_policy("0.2.0", "NARROW", "HEAD")
    with pytest.raises(ReleaseError, match="managed PASS"):
        validate_release_policy("0.3.0", "NARROW", "HEAD")
    with pytest.raises(ReleaseError, match="STOP"):
        validate_release_policy("0.2.0", "STOP", T2_COMMIT)


def test_release_builder_emits_constructed_pack_sbom_and_checksums(tmp_path: Path):
    outputs = build_release(ROOT, "HEAD", "0.3.0", "PASS", tmp_path)

    archive = outputs["archive"]
    with zipfile.ZipFile(archive) as pack:
        names = pack.namelist()
    assert "benchmark/reliability_reference/ATTRIBUTION.md" in names
    assert any(name.startswith("benchmark/reliability_reference/fixtures/") for name in names)
    assert not any(name.startswith("app/") or "/live_" in name for name in names)

    sbom = json.loads(outputs["sbom"].read_text(encoding="utf-8"))
    assert sbom["spdxVersion"] == "SPDX-2.3"
    assert sbom["dataLicense"] == "CC0-1.0"
    file_ids = [item["SPDXID"] for item in sbom["files"]]
    assert len(file_ids) == len(set(file_ids))
    assert all(value.startswith("SPDXRef-File-") for value in file_ids)
    checksums = outputs["checksums"].read_text(encoding="utf-8")
    assert archive.name in checksums
    assert outputs["sbom"].name in checksums


def test_managed_release_requires_pass_and_complete_teardown_absence():
    valid = {
        "result": "PASS",
        "baseline_commit": T2_COMMIT,
        "candidate_commit": "d" * 40,
        "managed_attempts": 1,
        "reason_code": "managed_conformance_pass",
        "bundle_hash": "a" * 64,
        "fixture_manifest_hash": "b" * 64,
        "claim_ledger_hash": "c" * 64,
        "candidate_tree_hash": "e" * 64,
        "first_deployment_utc": "2026-07-16T20:00:00Z",
        "deadline_utc": "2026-07-16T22:00:00Z",
        "scenario_results": [
            {"case_id": name, "result": "PASS"} for name in MANAGED_SCENARIOS
        ],
        "portable_comparison": {
            "result": "PASS",
            "scenarios": [{"case_id": name, "result": "PASS"} for name in MANAGED_SCENARIOS],
        },
        "delta_history": {
            name: [{"version": 0}]
            for name in ("staging", "states", "manifests", "current_pointer", "run_events")
        },
        "resource_inventory_before": [],
        "resource_inventory_after": [],
        "teardown": {
            "required": True,
            "verified": True,
            "job_absent": True,
            "schema_absent": True,
            "volume_absent": True,
            "tables_absent": True,
            "bundle_artifacts_absent": True,
        },
    }
    validate_managed_release_evidence(valid)

    with pytest.raises(ReleaseError, match="resource absence"):
        validate_managed_release_evidence(
            {**valid, "teardown": {**valid["teardown"], "volume_absent": False}}
        )

    with pytest.raises(ReleaseError, match="scenario completeness"):
        validate_managed_release_evidence(
            {**valid, "scenario_results": valid["scenario_results"][:-1]}
        )


def test_claim_ledger_separates_all_evidence_classes_and_forbidden_claims():
    ledger = json.loads((RELEASE_DOCS / "claim-ledger.json").read_text(encoding="utf-8"))
    classifications = {entry["classification"] for entry in ledger["entries"]}

    assert classifications == {"observed", "constructed", "derived", "prohibited"}
    prohibited = [entry for entry in ledger["entries"] if entry["classification"] == "prohibited"]
    assert prohibited and all(entry["publication"] == "prohibited" for entry in prohibited)


def test_terminal_narrow_evidence_template_and_visuals_are_identity_safe():
    evidence = json.loads((RELEASE_DOCS / "managed-proof.json").read_text(encoding="utf-8"))
    validate_managed_evidence(evidence)
    assert evidence["result"] == "NARROW"
    assert evidence["managed_attempts"] == 0
    assert evidence["managed_invocations"] == 3
    assert evidence["corrective_redeploys"] == 1
    assert evidence["scenario_results"] == []
    assert evidence["teardown"]["verified"] is True
    assert all(
        evidence["teardown"][field] is True
        for field in (
            "job_absent",
            "schema_absent",
            "volume_absent",
            "tables_absent",
            "bundle_artifacts_absent",
        )
    )
    assert redact_evidence(evidence) == evidence
    candidate = evidence["candidate_commit"]
    assert evidence["bundle_hash"] == hashlib.sha256(
        _blob(ROOT, candidate, "infra/databricks/reliability_reference/databricks.yml")
    ).hexdigest()
    assert evidence["fixture_manifest_hash"] == _fixture_manifest_hash(ROOT, candidate)
    assert evidence["candidate_tree_hash"] == _tree_manifest_hash(
        ROOT,
        candidate,
        "benchmark/reliability_reference",
        "infra/databricks/reliability_reference",
    )
    assert evidence["claim_ledger_hash"] == hashlib.sha256(
        (RELEASE_DOCS / "claim-ledger.json").read_bytes()
    ).hexdigest()

    template = json.loads(
        (RELEASE_DOCS / "managed-proof.template.json").read_text(encoding="utf-8")
    )
    assert template["result"] == "PENDING"
    assert template["managed_attempts"] == 0
    rendered = json.dumps({"evidence": evidence, "template": template})
    assert "@" not in rendered
    assert ".cloud.databricks.com" not in rendered
    assert "dapi" not in rendered

    for name in ("portable-managed-recovery.svg", "conformance-matrix.svg"):
        svg = (RELEASE_DOCS / name).read_text(encoding="utf-8")
        assert "<title" in svg and "<desc" in svg
        assert "@" not in svg and ".cloud.databricks.com" not in svg


@pytest.mark.parametrize(
    "fault_at", ["after_stage", "after_validation", "before_pointer_swap"]
)
def test_managed_state_protocol_preserves_pointer_and_retry_matches_clean_rebuild(fault_at: str):
    store = MemoryManagedStore()
    interrupted = _execute_managed_case(
        "delta",
        json.loads((SCENARIOS / "008_interrupted_publish.json").read_text(encoding="utf-8")),
        store=store,
        normalizer=normalize_object,
        fault_at=fault_at,
    )
    pointer_after_failure = store.load("008_interrupted_publish")

    assert interrupted.terminal_status == "interrupted"
    assert pointer_after_failure["state_hash"] == interrupted.state_hash
    assert {row["rental_id"] for row in interrupted.canonical_rows} == {"2001", "2002"}

    retry = _execute_managed_case(
        "delta",
        json.loads((SCENARIOS / "008_interrupted_publish.json").read_text(encoding="utf-8")),
        store=store,
        normalizer=normalize_object,
    )
    clean = _execute_managed_case(
        "delta",
        json.loads((SCENARIOS / "009_full_rebuild.json").read_text(encoding="utf-8")),
        store=MemoryManagedStore(),
        normalizer=normalize_object,
    )

    assert retry.state_hash == clean.state_hash
    assert retry.canonical_rows == clean.canonical_rows


def test_managed_report_gate_requires_all_oracle_cases_and_fault_invariants():
    normal_results = []
    for scenario_name in MANAGED_SCENARIOS:
        result = _execute_managed_case(
            "delta",
            json.loads((SCENARIOS / f"{scenario_name}.json").read_text(encoding="utf-8")),
            store=MemoryManagedStore(),
            normalizer=normalize_object,
        )
        normal_results.append({"scenario": scenario_name, "result": result.to_dict()})
    fault_results = []
    for fault in ("after_stage", "after_validation", "before_pointer_swap"):
        store = MemoryManagedStore()
        interrupted = _execute_managed_case(
            "delta",
            json.loads((SCENARIOS / "008_interrupted_publish.json").read_text(encoding="utf-8")),
            store=store,
            normalizer=normalize_object,
            fault_at=fault,
        )
        pointer = store.load("008_interrupted_publish")
        retry = _execute_managed_case(
            "delta",
            json.loads((SCENARIOS / "008_interrupted_publish.json").read_text(encoding="utf-8")),
            store=store,
            normalizer=normalize_object,
        )
        fault_results.append(
            {
                "scenario": "008_interrupted_publish",
                "fault_at": fault,
                "interrupted": interrupted.to_dict(),
                "pointer_after_fault": {
                    "state_version": pointer["state_version"],
                    "state_hash": pointer["state_hash"],
                },
                "retry": retry.to_dict(),
            }
        )
    results = [*normal_results, *fault_results]

    validate_managed_scenario_results(results)

    broken = json.loads(json.dumps(results))
    broken[0]["result"]["state_hash"] = "sha256:wrong"
    with pytest.raises(EvidenceError, match="oracle"):
        validate_managed_scenario_results(broken)
