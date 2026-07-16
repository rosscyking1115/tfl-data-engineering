"""Bounded Databricks Delta execution for the reliability-reference candidate.

This module is deliberately not exported by the package CLI.  It requires an
already-authenticated Databricks Spark session and uniquely scoped resources.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .constants import CONTRACT_VERSION, EMPTY_STATE_HASH, VERSION
from .contracts import ContractError, ObjectValidationError, load_json, load_sidecar
from .managed_evidence import EvidenceError, resource_names
from .models import RunResult

FaultPoint = str | None
Normalizer = Callable[[Path, dict[str, Any]], list[dict[str, Any]]]

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validated_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise EvidenceError(f"unsafe Databricks identifier: {value!r}")
    return value


def _quoted(value: str) -> str:
    return f"`{_validated_identifier(value)}`"


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@dataclass(frozen=True)
class DeltaTableNames:
    """Validated, fully-qualified names for the five T3-owned Delta tables."""

    catalog: str
    schema: str

    def __post_init__(self) -> None:
        _validated_identifier(self.catalog)
        _validated_identifier(self.schema)

    def _table(self, name: str) -> str:
        return f"{_quoted(self.catalog)}.{_quoted(self.schema)}.{_quoted(name)}"

    @property
    def staging(self) -> str:
        return self._table("staging")

    @property
    def states(self) -> str:
        return self._table("states")

    @property
    def manifests(self) -> str:
        return self._table("manifests")

    @property
    def current_pointer(self) -> str:
        return self._table("current_pointer")

    @property
    def run_events(self) -> str:
        return self._table("run_events")

    def all(self) -> tuple[str, ...]:
        return (
            self.staging,
            self.states,
            self.manifests,
            self.current_pointer,
            self.run_events,
        )


class ManagedStore(Protocol):
    def load(self, case_id: str) -> dict[str, Any]: ...

    def stage(
        self,
        run_id: str,
        case_id: str,
        candidate: dict[str, Any],
        operation: dict[str, Any],
    ) -> None: ...

    def prepare_state(self, case_id: str, candidate: dict[str, Any]) -> str: ...

    def commit_pointer(self, case_id: str, version: str) -> dict[str, Any]: ...

    def record_run(self, run_id: str, manifest: dict[str, Any]) -> str: ...

    def artifact_references(self, manifest_ref: str) -> dict[str, str]: ...


def _empty_state() -> dict[str, Any]:
    return {
        "state_version": None,
        "state_hash": EMPTY_STATE_HASH,
        "canonical_rows": [],
        "applied_hashes": [],
        "active_objects": {},
    }


def _period_contains(row: dict[str, Any], metadata: dict[str, Any]) -> bool:
    row_date = row["start_ts_local"][:10]
    period = metadata["ownership_period"]
    return period["start"] <= row_date <= period["end"]


def _periods_overlap(left: dict[str, str], right: dict[str, str]) -> bool:
    return left["start"] <= right["end"] and right["start"] <= left["end"]


def _row_identity(row: dict[str, Any]) -> tuple[str, str]:
    return row["schema_family"], row["rental_id"]


def _managed_result(
    *,
    case_id: str,
    engine: str,
    terminal_status: str,
    state: dict[str, Any],
    history: list[dict[str, Any]],
    reconciliation: list[dict[str, Any]],
    store: ManagedStore,
    manifest_ref: str,
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
        artifacts=store.artifact_references(manifest_ref),
    )


def _execute_managed_case(
    engine: str,
    case_definition: str | Path | Mapping[str, Any],
    *,
    store: ManagedStore,
    normalizer: Normalizer,
    fault_at: FaultPoint = None,
) -> RunResult:
    """Execute shared recovery semantics against a managed state store."""

    if engine != "delta":
        raise ContractError(f"unsupported managed engine: {engine}")
    if fault_at not in {None, "after_stage", "after_validation", "before_pointer_swap"}:
        raise ContractError(f"unsupported fault point: {fault_at}")
    case = dict(case_definition) if isinstance(case_definition, Mapping) else load_json(Path(case_definition))
    if case.get("contract_version") != CONTRACT_VERSION:
        raise ContractError(f"{case.get('case_id')}: unsupported contract version")

    case_id = str(case["case_id"])
    state = store.load(case_id)
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
            rows = normalizer(fixture, metadata)
            supersedes = metadata["supersedes_object_id"]
            if supersedes:
                previous = state["active_objects"].get(supersedes)
                if previous is None:
                    raise ObjectValidationError("unknown_superseded_object", supersedes)
                if previous["ownership_period"] != metadata["ownership_period"]:
                    raise ObjectValidationError(
                        "ownership_period_mismatch", "replacement ownership differs"
                    )
                retained_rows = [
                    row for row in state["canonical_rows"] if not _period_contains(row, metadata)
                ]
            else:
                retained_rows = list(state["canonical_rows"])
                for active in state["active_objects"].values():
                    if _periods_overlap(active["ownership_period"], metadata["ownership_period"]):
                        raise ObjectValidationError(
                            "ownership_period_overlap",
                            f"ownership overlaps active object {active['object_id']}",
                        )
            retained_identities = {_row_identity(row) for row in retained_rows}
            duplicate_identity = next(
                (_row_identity(row) for row in rows if _row_identity(row) in retained_identities),
                None,
            )
            if duplicate_identity:
                raise ObjectValidationError(
                    "duplicate_state_identity",
                    f"identity {duplicate_identity!r} already exists in active state",
                )
        except ObjectValidationError as error:
            event = {
                **base,
                "disposition": "rejected",
                "reason_code": error.code,
                "reason": error.code,
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
        store.stage(run_id, case_id, candidate, operation)
        inject = bool(fault_at and operation.get("fault_target", False))
        if inject and fault_at in {"after_stage", "after_validation"}:
            manifest_ref = store.record_run(
                run_id,
                {"case_id": case_id, "status": "interrupted", "fault_at": fault_at},
            )
            return _managed_result(
                case_id=case_id,
                engine=engine,
                terminal_status="interrupted",
                state=state,
                history=history,
                reconciliation=reconciliation,
                store=store,
                manifest_ref=manifest_ref,
            )
        version = store.prepare_state(case_id, candidate)
        if inject and fault_at == "before_pointer_swap":
            manifest_ref = store.record_run(
                run_id,
                {
                    "case_id": case_id,
                    "status": "interrupted",
                    "fault_at": fault_at,
                    "prepared_state": version,
                },
            )
            return _managed_result(
                case_id=case_id,
                engine=engine,
                terminal_status="interrupted",
                state=state,
                history=history,
                reconciliation=reconciliation,
                store=store,
                manifest_ref=manifest_ref,
            )
        state = store.commit_pointer(case_id, version)
        event["state_hash_after"] = state["state_hash"]
        reconciliation.append(event)
        history.append({"object_id": metadata["object_id"], "disposition": disposition})

    manifest_ref = store.record_run(
        run_id,
        {
            "benchmark_version": VERSION,
            "contract_version": CONTRACT_VERSION,
            "case_id": case_id,
            "engine": engine,
            "status": "success",
            "state_hash": state["state_hash"],
            "fixture_hashes": [item["content_sha256"] for item in reconciliation],
        },
    )
    return _managed_result(
        case_id=case_id,
        engine=engine,
        terminal_status="success",
        state=state,
        history=history,
        reconciliation=reconciliation,
        store=store,
        manifest_ref=manifest_ref,
    )


class DeltaStateStore:
    """Small Delta-backed store with an atomic per-case current pointer."""

    def __init__(self, spark: Any, catalog: str, schema: str, run_scope: str):
        resource_names(run_scope)
        self.spark = spark
        self.names = DeltaTableNames(catalog, schema)
        self.run_scope = run_scope

    def ensure_tables(self) -> None:
        definitions = {
            self.names.staging: "run_scope STRING, run_id STRING, case_id STRING, candidate_json STRING, operation_json STRING",
            self.names.states: "run_scope STRING, case_id STRING, state_version STRING, state_hash STRING, row_json STRING",
            self.names.manifests: "run_scope STRING, case_id STRING, state_version STRING, state_hash STRING, state_json STRING",
            self.names.current_pointer: "run_scope STRING, case_id STRING, state_version STRING, state_hash STRING",
            self.names.run_events: "run_scope STRING, run_id STRING, case_id STRING, status STRING, manifest_json STRING",
        }
        for table, columns in definitions.items():
            self.spark.sql(f"CREATE TABLE IF NOT EXISTS {table} ({columns}) USING DELTA")

    def _append(self, table: str, row: dict[str, str]) -> None:
        from pyspark.sql.types import StringType, StructField, StructType

        schema = StructType([StructField(key, StringType(), False) for key in row])
        frame = self.spark.createDataFrame([tuple(row.values())], schema=schema)
        frame.write.mode("append").saveAsTable(table.replace("`", ""))

    def load(self, case_id: str) -> dict[str, Any]:
        query = f"""
            SELECT m.state_json
            FROM {self.names.current_pointer} p
            JOIN {self.names.manifests} m
              ON p.run_scope = m.run_scope
             AND p.case_id = m.case_id
             AND p.state_version = m.state_version
            WHERE p.run_scope = {_literal(self.run_scope)}
              AND p.case_id = {_literal(case_id)}
            LIMIT 1
        """
        rows = self.spark.sql(query).collect()
        return json.loads(rows[0]["state_json"]) if rows else _empty_state()

    def stage(
        self,
        run_id: str,
        case_id: str,
        candidate: dict[str, Any],
        operation: dict[str, Any],
    ) -> None:
        self._append(
            self.names.staging,
            {
                "run_scope": self.run_scope,
                "run_id": run_id,
                "case_id": case_id,
                "candidate_json": json.dumps(candidate, sort_keys=True, separators=(",", ":")),
                "operation_json": json.dumps(operation, sort_keys=True, separators=(",", ":")),
            },
        )

    def prepare_state(self, case_id: str, candidate: dict[str, Any]) -> str:
        from .canonical import ordered_rows, state_hash

        rows = ordered_rows(candidate["canonical_rows"])
        digest = state_hash(rows)
        version = f"v-{digest.removeprefix('sha256:')[:16]}"
        existing = self.spark.sql(
            f"SELECT count(*) AS n FROM {self.names.manifests} "
            f"WHERE run_scope = {_literal(self.run_scope)} "
            f"AND case_id = {_literal(case_id)} AND state_version = {_literal(version)}"
        ).collect()[0]["n"]
        if not existing:
            state = {
                **candidate,
                "state_version": version,
                "state_hash": digest,
                "canonical_rows": rows,
            }
            for row in rows:
                self._append(
                    self.names.states,
                    {
                        "run_scope": self.run_scope,
                        "case_id": case_id,
                        "state_version": version,
                        "state_hash": digest,
                        "row_json": json.dumps(row, sort_keys=True, separators=(",", ":")),
                    },
                )
            self._append(
                self.names.manifests,
                {
                    "run_scope": self.run_scope,
                    "case_id": case_id,
                    "state_version": version,
                    "state_hash": digest,
                    "state_json": json.dumps(state, sort_keys=True, separators=(",", ":")),
                },
            )
        return version

    def commit_pointer(self, case_id: str, version: str) -> dict[str, Any]:
        state_rows = self.spark.sql(
            f"SELECT state_hash, state_json FROM {self.names.manifests} "
            f"WHERE run_scope = {_literal(self.run_scope)} "
            f"AND case_id = {_literal(case_id)} AND state_version = {_literal(version)} LIMIT 1"
        ).collect()
        if not state_rows:
            raise EvidenceError(f"prepared state is absent: {case_id}/{version}")
        digest = state_rows[0]["state_hash"]
        source = (
            f"SELECT {_literal(self.run_scope)} run_scope, {_literal(case_id)} case_id, "
            f"{_literal(version)} state_version, {_literal(digest)} state_hash"
        )
        self.spark.sql(
            f"""
            MERGE INTO {self.names.current_pointer} AS target
            USING ({source}) AS source
            ON target.run_scope = source.run_scope AND target.case_id = source.case_id
            WHEN MATCHED THEN UPDATE SET
              state_version = source.state_version, state_hash = source.state_hash
            WHEN NOT MATCHED THEN INSERT *
            """
        )
        return json.loads(state_rows[0]["state_json"])

    def record_run(self, run_id: str, manifest: dict[str, Any]) -> str:
        self._append(
            self.names.run_events,
            {
                "run_scope": self.run_scope,
                "run_id": run_id,
                "case_id": str(manifest["case_id"]),
                "status": str(manifest["status"]),
                "manifest_json": json.dumps(manifest, sort_keys=True, separators=(",", ":")),
            },
        )
        return f"delta/run_events/{run_id}"

    def artifact_references(self, manifest_ref: str) -> dict[str, str]:
        return {
            "current_pointer": "delta/current_pointer",
            "run_manifest": manifest_ref,
        }

    def cleanup_statements(self) -> tuple[str, ...]:
        return tuple(f"DROP TABLE IF EXISTS {table}" for table in self.names.all())


def run_managed_case(
    spark: Any,
    case_definition: str | Path | Mapping[str, Any],
    *,
    catalog: str,
    schema: str,
    run_scope: str,
    fault_at: FaultPoint = None,
) -> RunResult:
    """Run one bounded case in a caller-supplied Databricks Spark session."""

    from .delta_adapter import normalize_object

    store = DeltaStateStore(spark, catalog, schema, run_scope)
    store.ensure_tables()
    return _execute_managed_case(
        "delta",
        case_definition,
        store=store,
        normalizer=lambda fixture, metadata: normalize_object(spark, fixture, metadata),
        fault_at=fault_at,
    )
