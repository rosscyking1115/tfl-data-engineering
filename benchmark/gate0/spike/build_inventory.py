"""Refresh source metadata and build the bounded Gate 0 incident inventory.

The public bucket listing is metadata-only. This script never downloads source
objects; hashes and row counts are populated only for the locally retained files.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ingestion.gate0_cycle_inventory import list_bucket

from .runner import CONTRACT_PATH, header_variant_id

ROOT = Path(__file__).parents[3]
HISTORICAL_INVENTORY = ROOT / "docs" / "gate0" / "cycle_file_inventory.csv"
RECONCILIATION = ROOT / "docs" / "phase1" / "backfill_reconciliation.csv"
LOCAL_SOURCE = ROOT / "data" / "raw" / "usage-stats"
EVIDENCE_DIR = ROOT / "docs" / "gate0" / "reliability-reference"
PERIOD_RE = re.compile(r"JourneyDataExtract(\d{1,2}[A-Za-z]{3}\d{2,4})-(\d{1,2}[A-Za-z]{3}\d{2,4})")


INCIDENT_VARIANTS = {
    "classic_missing_end_station_id": "missing_end_station_identifier",
    "nextgen_station_names_first": "reordered_header",
    "nextgen_interleaved_station_order": "reordered_header",
}


def _parse_date_token(token: str) -> datetime:
    for format_string in ("%d%b%Y", "%d%b%y"):
        try:
            return datetime.strptime(token, format_string)
        except ValueError:
            continue
    raise ValueError(token)


def parse_publication_period(key: str) -> tuple[str, str] | None:
    """Parse the stated extract period without inferring one for archive bundles."""
    match = PERIOD_RE.search(key)
    if not match:
        return None
    try:
        start, end = (_parse_date_token(token).date().isoformat() for token in match.groups())
    except ValueError:
        return None
    return start, end


def classify_incident(variant_key: str | None, object_name: str) -> str:
    """Classify only incidents directly observed in retained source bytes."""
    if "444JourneyDataExtract" in object_name:
        return "partial_boundary_date"
    return INCIDENT_VARIANTS.get(variant_key, "none")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _header(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [name.strip() for name in next(csv.reader(handle)) if name.strip()]


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _boundary_spill_rows(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return sum(1 for row in reader if (row.get("Start date") or "").startswith("2026-06-01"))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _variant_index() -> dict[tuple[str, ...], dict[str, Any]]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return {tuple(variant["headers"]): variant for variant in contract["variants"]}


def build_source_inventory(current_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Combine refreshed metadata with local-only hashes and Phase 1 counts."""
    recon = {row["source_file"]: row for row in _load_csv(RECONCILIATION)}
    local = {path.name: path for path in LOCAL_SOURCE.glob("*.csv")}
    variants = _variant_index()
    periods: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in current_rows:
        period = parse_publication_period(row["key"])
        if period:
            periods[period].append(row["key"])

    result = []
    for object_row in current_rows:
        key = object_row["key"]
        name = Path(key).name
        period = parse_publication_period(key)
        path = local.get(name)
        variant = None
        digest = ""
        fields: list[str] = []
        spill_rows = ""
        if path is not None:
            fields = _header(path)
            variant = variants.get(tuple(fields))
            digest = _hash_file(path)
            if "444JourneyDataExtract" in name:
                spill_rows = str(_boundary_spill_rows(path))
        variant_key = variant["variant_key"] if variant else None
        counts = recon.get(name, {})
        same_period = periods.get(period, []) if period else []
        supersession_evidence = ""
        if len(same_period) > 1:
            supersession_evidence = "multiple objects declare the same publication period; no ordering inferred"
        incident = classify_incident(variant_key, name) if path is not None else "unknown_not_retained"
        notes = ""
        if spill_rows:
            notes = f"{spill_rows} locally observed starts on 2026-06-01 beyond the filename end date"
        result.append(
            {
                "object_key": key,
                "size_bytes": object_row["size_bytes"],
                "last_modified": object_row["last_modified"],
                "publication_period_start": period[0] if period else "",
                "publication_period_end": period[1] if period else "",
                "schema_family": variant["schema_family"] if variant else "",
                "header_variant_id": header_variant_id(fields) if fields else "",
                "header_variant_key": variant_key or "",
                "local_retained": str(path is not None).lower(),
                "local_size_matches_listing": (
                    str(path.stat().st_size == int(object_row["size_bytes"])).lower() if path else ""
                ),
                "content_sha256": digest,
                "raw_rows": counts.get("raw_rows", ""),
                "silver_rows": counts.get("silver_rows", ""),
                "quarantine_rows": counts.get("quarantine_rows", ""),
                "reconciliation_delta": counts.get("delta", ""),
                "supersedes_object_key": "",
                "supersession_evidence": supersession_evidence,
                "evidence_class": "observed",
                "incident_classification": incident,
                "publication_status": "metadata_and_local_hash" if path else "metadata_only",
                "notes": notes,
            }
        )
    return result


def compare_listings(
    historical_rows: list[dict[str, Any]],
    current_rows: list[dict[str, Any]],
    observed_at: str,
) -> dict[str, Any]:
    old = {row["key"]: row for row in historical_rows}
    new = {row["key"]: row for row in current_rows}
    common = old.keys() & new.keys()
    changed = [
        key
        for key in sorted(common)
        if str(old[key]["size_bytes"]) != str(new[key]["size_bytes"])
        or old[key]["last_modified"] != new[key]["last_modified"]
    ]
    return {
        "historical_snapshot": {
            "path": "docs/gate0/cycle_file_inventory.csv",
            "object_count": len(historical_rows),
            "latest_object_last_modified": max(row["last_modified"] for row in historical_rows),
            "interpretation": "retained historical metadata snapshot; not a current bucket count",
        },
        "refreshed_snapshot": {
            "observed_at_utc": observed_at,
            "object_count": len(current_rows),
            "latest_object_last_modified": max(row["last_modified"] for row in current_rows),
        },
        "added_keys": sorted(new.keys() - old.keys()),
        "removed_keys": sorted(old.keys() - new.keys()),
        "metadata_changed_keys": changed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    args = parser.parse_args()
    observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    historical_rows = _load_csv(HISTORICAL_INVENTORY)
    current_rows = list_bucket("usage-stats/")
    listing_rows = [
        {
            "key": row["key"],
            "size_bytes": row["size_bytes"],
            "last_modified": row["last_modified"],
            "ext": row["ext"],
            "observed_at_utc": observed_at,
        }
        for row in current_rows
    ]
    snapshot_path = EVIDENCE_DIR / f"source-listing-snapshot-{args.date}.csv"
    _write_csv(snapshot_path, listing_rows, list(listing_rows[0]))

    comparison = compare_listings(historical_rows, current_rows, observed_at)
    comparison_path = EVIDENCE_DIR / "listing-comparison.json"
    comparison_path.parent.mkdir(parents=True, exist_ok=True)
    comparison_path.write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")

    incident_rows = build_source_inventory(current_rows)
    incident_path = EVIDENCE_DIR / "source-incident-inventory.csv"
    _write_csv(incident_path, incident_rows, list(incident_rows[0]))
    retained = sum(row["local_retained"] == "true" for row in incident_rows)
    print(f"refreshed listing: {len(current_rows)} objects at {observed_at}")
    print(f"retained evidence: {retained} objects hashed and reconciled where counts exist")
    print(f"snapshot: {snapshot_path}")
    print(f"comparison: {comparison_path}")
    print(f"incident inventory: {incident_path}")


if __name__ == "__main__":
    main()
