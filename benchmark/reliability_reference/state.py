"""Versioned local state and atomic pointer publication."""

import json
import os
from pathlib import Path
from typing import Any, Callable

from .canonical import ordered_rows, state_hash
from .constants import EMPTY_STATE_HASH


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


class StateStore:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.staging = workspace / "staging"
        self.states = workspace / "states"
        self.runs = workspace / "runs"
        for path in (self.staging, self.states, self.runs):
            path.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        pointer = self.workspace / "current.json"
        if not pointer.exists():
            return {
                "state_version": None,
                "state_hash": EMPTY_STATE_HASH,
                "canonical_rows": [],
                "applied_hashes": [],
                "active_objects": {},
            }
        current = json.loads(pointer.read_text(encoding="utf-8"))
        manifest = self.states / current["state_version"] / "state.json"
        return json.loads(manifest.read_text(encoding="utf-8"))

    def stage(self, run_id: str, payload: dict[str, Any]) -> Path:
        stage = self.staging / run_id
        stage.mkdir(parents=True, exist_ok=True)
        _write_json(stage / "candidate.json", payload)
        return stage

    def prepare_state(
        self,
        payload: dict[str, Any],
        parquet_writer: Callable[[list[dict[str, Any]], Path], None],
    ) -> str:
        rows = ordered_rows(payload["canonical_rows"])
        digest = state_hash(rows)
        version = f"v-{digest.removeprefix('sha256:')[:16]}"
        destination = self.states / version
        destination.mkdir(parents=True, exist_ok=True)
        manifest = {**payload, "state_version": version, "state_hash": digest, "canonical_rows": rows}
        _write_json(destination / "canonical.json", rows)
        parquet_writer(rows, destination / "canonical.parquet")
        _write_json(destination / "state.json", manifest)
        return version

    def commit_pointer(self, version: str) -> dict[str, Any]:
        state = json.loads((self.states / version / "state.json").read_text(encoding="utf-8"))
        pointer = {"state_version": version, "state_hash": state["state_hash"]}
        temporary = self.workspace / "current.json.tmp"
        _write_json(temporary, pointer)
        os.replace(temporary, self.workspace / "current.json")
        return state

    def record_run(self, run_id: str, manifest: dict[str, Any]) -> Path:
        path = self.runs / run_id / "manifest.json"
        _write_json(path, manifest)
        return path
