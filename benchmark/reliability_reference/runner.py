"""Engine-neutral scenario orchestration and recovery protocol."""

import tempfile
import uuid
from pathlib import Path
from typing import Any, Literal, Mapping

from .constants import CONTRACT_VERSION, VERSION
from .contracts import (
    ContractError,
    ObjectValidationError,
    load_json,
    load_sidecar,
    validate_workspace,
)
from .duckdb_adapter import normalize_object as normalize_duckdb
from .models import RunResult
from .state import StateStore

FaultPoint = Literal["after_stage", "after_validation", "before_pointer_swap"]


def _period_contains(row: dict[str, Any], metadata: dict[str, Any]) -> bool:
    row_date = row["start_ts_local"][:10]
    return metadata["ownership_period"]["start"] <= row_date <= metadata["ownership_period"]["end"]


def _result(
    case_id: str,
    engine: str,
    terminal_status: str,
    state: dict[str, Any],
    history: list[dict[str, Any]],
    reconciliation: list[dict[str, Any]],
    run_manifest: Path,
    workspace: Path,
) -> RunResult:
    return RunResult(
        benchmark_version=VERSION,
        contract_version=CONTRACT_VERSION,
        case_id=case_id,
        engine=engine,
        terminal_status=terminal_status,
        canonical_rows=state["canonical_rows"],
        object_history=history,
        reconciliation=reconciliation,
        current_state_version=state["state_version"],
        state_hash=state["state_hash"],
        artifacts={
            "current_pointer": "current.json",
            "run_manifest": run_manifest.relative_to(workspace).as_posix(),
        },
    )


def run_case(
    engine: Literal["duckdb", "spark"],
    case_definition: str | Path | Mapping[str, Any],
    *,
    workspace: Path | None = None,
    fault_at: FaultPoint | None = None,
) -> RunResult:
    if engine not in {"duckdb", "spark"}:
        raise ContractError(f"unsupported engine: {engine}")
    case = dict(case_definition) if isinstance(case_definition, Mapping) else load_json(Path(case_definition))
    if case.get("contract_version") != CONTRACT_VERSION:
        raise ContractError(f"{case.get('case_id')}: unsupported contract version")
    workspace = validate_workspace(
        Path(tempfile.mkdtemp(prefix="tfl-reliability-")) if workspace is None else Path(workspace)
    )
    workspace.mkdir(parents=True, exist_ok=True)
    store = StateStore(workspace)
    state = store.load()
    history: list[dict[str, Any]] = []
    reconciliation: list[dict[str, Any]] = []
    run_id = f"run-{uuid.uuid4().hex}"

    for operation in case["operations"]:
        metadata, fixture = load_sidecar(operation["object_ref"])
        before_hash = state["state_hash"]
        base = {
            "object_id": metadata["object_id"],
            "content_sha256": metadata["content_sha256"],
            "state_hash_before": before_hash,
            "removed_rows": 0,
            "quarantined_rows": 0,
        }
        if metadata["content_sha256"] in state["applied_hashes"]:
            event = {
                **base,
                "disposition": "duplicate",
                "reason_code": "exact_content_replay",
                "input_rows": metadata["expected_source_rows"],
                "accepted_rows": 0,
                "rejected_rows": 0,
                "state_hash_after": before_hash,
            }
            reconciliation.append(event)
            history.append({"object_id": metadata["object_id"], "disposition": "duplicate"})
            continue

        try:
            if engine == "duckdb":
                rows = normalize_duckdb(fixture, metadata)
            else:
                from .spark_adapter import normalize_object as normalize_spark

                rows = normalize_spark(fixture, metadata)
            supersedes = metadata["supersedes_object_id"]
            if supersedes:
                previous = state["active_objects"].get(supersedes)
                if previous is None:
                    raise ObjectValidationError("unknown_superseded_object", supersedes)
                if previous["ownership_period"] != metadata["ownership_period"]:
                    raise ObjectValidationError(
                        "ownership_period_mismatch", "replacement ownership differs"
                    )
        except ObjectValidationError as error:
            event = {
                **base,
                "disposition": "rejected",
                "reason_code": error.code,
                "reason": str(error),
                "input_rows": metadata["expected_source_rows"],
                "accepted_rows": 0,
                "rejected_rows": metadata["expected_source_rows"],
                "state_hash_after": before_hash,
            }
            reconciliation.append(event)
            history.append({"object_id": metadata["object_id"], "disposition": "rejected"})
            continue

        candidate_rows = list(state["canonical_rows"])
        active_objects = dict(state["active_objects"])
        removed = 0
        disposition = "accepted"
        supersedes = metadata["supersedes_object_id"]
        if supersedes:
            retained = [row for row in candidate_rows if not _period_contains(row, metadata)]
            removed = len(candidate_rows) - len(retained)
            candidate_rows = retained
            active_objects.pop(supersedes, None)
            disposition = "replaced"
        candidate_rows.extend(rows)
        active_objects[metadata["object_id"]] = metadata
        candidate = {
            "canonical_rows": candidate_rows,
            "applied_hashes": sorted({*state["applied_hashes"], metadata["content_sha256"]}),
            "active_objects": active_objects,
        }
        event = {
            **base,
            "disposition": disposition,
            "reason_code": "",
            "input_rows": len(rows),
            "accepted_rows": len(rows),
            "rejected_rows": 0,
            "removed_rows": removed,
        }
        stage = store.stage(run_id, {**candidate, "operation": operation})
        inject = fault_at and operation.get("fault_target", False)
        if inject and fault_at == "after_stage":
            manifest = store.record_run(
                run_id,
                {"case_id": case["case_id"], "status": "interrupted", "fault_at": fault_at},
            )
            return _result(case["case_id"], engine, "interrupted", state, history, reconciliation, manifest, workspace)
        if inject and fault_at == "after_validation":
            manifest = store.record_run(
                run_id,
                {"case_id": case["case_id"], "status": "interrupted", "fault_at": fault_at},
            )
            return _result(case["case_id"], engine, "interrupted", state, history, reconciliation, manifest, workspace)
        version = store.prepare_state(candidate)
        if inject and fault_at == "before_pointer_swap":
            manifest = store.record_run(
                run_id,
                {
                    "case_id": case["case_id"],
                    "status": "interrupted",
                    "fault_at": fault_at,
                    "prepared_state": version,
                },
            )
            return _result(case["case_id"], engine, "interrupted", state, history, reconciliation, manifest, workspace)
        state = store.commit_pointer(version)
        event["state_hash_after"] = state["state_hash"]
        reconciliation.append(event)
        history.append({"object_id": metadata["object_id"], "disposition": disposition})
        (stage / "published").touch()

    manifest = store.record_run(
        run_id,
        {
            "benchmark_version": VERSION,
            "contract_version": CONTRACT_VERSION,
            "case_id": case["case_id"],
            "engine": engine,
            "status": "success",
            "state_hash": state["state_hash"],
            "fixture_hashes": [item["content_sha256"] for item in reconciliation],
        },
    )
    return _result(case["case_id"], engine, "success", state, history, reconciliation, manifest, workspace)
