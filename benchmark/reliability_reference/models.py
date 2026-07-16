"""Stable JSON-facing result types."""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RunResult:
    benchmark_version: str
    contract_version: str
    case_id: str
    engine: str
    terminal_status: str
    canonical_rows: list[dict[str, Any]]
    object_history: list[dict[str, Any]]
    reconciliation: list[dict[str, Any]]
    current_state_version: str | None
    state_hash: str
    artifacts: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
