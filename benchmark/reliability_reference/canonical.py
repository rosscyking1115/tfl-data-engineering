"""Canonical value and semantic state rules shared by both adapters."""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .contracts import ObjectValidationError

LONDON = ZoneInfo("Europe/London")


def normalized_text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text or None


def required_text(value: Any, field: str) -> str:
    text = normalized_text(value)
    if text is None:
        raise ObjectValidationError("invalid_required_value", f"{field} is required")
    return text


def parse_source_time(value: Any, formats: list[str], field: str) -> datetime:
    text = required_text(value, field)
    parsed = None
    for format_string in formats:
        try:
            parsed = datetime.strptime(text, format_string)
            break
        except ValueError:
            continue
    if parsed is None:
        raise ObjectValidationError("invalid_timestamp", f"unsupported {field}: {text!r}")
    candidates = []
    for fold in (0, 1):
        aware = parsed.replace(tzinfo=LONDON, fold=fold)
        round_trip = aware.astimezone(timezone.utc).astimezone(LONDON).replace(tzinfo=None)
        if round_trip == parsed:
            candidates.append(aware)
    offsets = {candidate.utcoffset() for candidate in candidates}
    if not candidates:
        raise ObjectValidationError(
            "nonexistent_source_time", f"nonexistent Europe/London {field}: {text!r}"
        )
    if len(offsets) > 1:
        raise ObjectValidationError(
            "ambiguous_source_time", f"ambiguous Europe/London {field}: {text!r}"
        )
    return candidates[0]


def row_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return row["schema_family"], row["rental_id"], row["source_object_id"]


def ordered_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=row_sort_key)


def state_hash(rows: list[dict[str, Any]]) -> str:
    encoded = json.dumps(
        ordered_rows(rows),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
