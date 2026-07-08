"""Durable live layer: pull TfL Line Status + BikePoint occupancy and append a
compact daily snapshot to committed Parquet (no warehouse). Run by the daily
GitHub Actions cron; idempotent per snapshot date (safe to re-run / catch up).

Compact by design: ~800 dock rows + ~20 line rows per day → single-digit MB/year,
fine to commit for years. Feeds the Streamlit "today's network" panel.
"""

from datetime import datetime, timezone
from pathlib import Path
import argparse

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "gold_export"
API = "https://api.tfl.gov.uk"
RAIL_MODES = "tube,dlr,overground,elizabeth-line,tram"


def prop(place: dict, key: str):
    for p in place.get("additionalProperties", []):
        if p.get("key") == key:
            return p.get("value")
    return None


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def upsert(path: Path, df: pd.DataFrame, date_col: str, snapshot_date: str) -> None:
    """Replace any existing rows for snapshot_date, then append — idempotent."""
    if path.exists():
        prev = pd.read_parquet(path)
        prev = prev[prev[date_col] != snapshot_date]
        df = pd.concat([prev, df], ignore_index=True)
    df.to_parquet(path, index=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    args = ap.parse_args()
    day = args.date
    pulled_at = datetime.now(timezone.utc).isoformat()
    OUT.mkdir(parents=True, exist_ok=True)
    s = requests.Session()

    bp = s.get(f"{API}/BikePoint", timeout=60); bp.raise_for_status(); bp = bp.json()
    ls = s.get(f"{API}/Line/Mode/{RAIL_MODES}/Status", timeout=60); ls.raise_for_status(); ls = ls.json()
    if len(bp) < 700 or len(ls) < 15:
        raise SystemExit(f"quality gate: {len(bp)} bikepoints / {len(ls)} lines (expected ~800/~20)")

    bp_df = pd.DataFrame([{
        "snapshot_date": day, "pulled_at": pulled_at,
        "bikepoint_id": p.get("id"), "common_name": p.get("commonName"),
        "lat": p.get("lat"), "lon": p.get("lon"),
        "n_bikes": as_int(prop(p, "NbBikes")), "n_empty_docks": as_int(prop(p, "NbEmptyDocks")),
        "n_docks": as_int(prop(p, "NbDocks")), "n_ebikes": as_int(prop(p, "NbEBikes")),
    } for p in bp])
    bp_df["fill_rate"] = (bp_df["n_bikes"] / bp_df["n_docks"].replace(0, pd.NA)).round(3)

    ls_rows = []
    for ln in ls:
        for st in ln.get("lineStatuses", [{}]):
            ls_rows.append({
                "snapshot_date": day, "pulled_at": pulled_at,
                "line_id": ln.get("id"), "line_name": ln.get("name"), "mode": ln.get("modeName"),
                "status_severity": st.get("statusSeverity"),
                "status_description": st.get("statusSeverityDescription"),
                "is_good_service": st.get("statusSeverity") == 10,
                "reason": st.get("reason"),
            })
    ls_df = pd.DataFrame(ls_rows)

    upsert(OUT / "live_bikepoint.parquet", bp_df, "snapshot_date", day)
    upsert(OUT / "live_line_status.parquet", ls_df, "snapshot_date", day)
    disrupted = int((ls_df["is_good_service"] == False).sum())  # noqa: E712
    print(f"[OK] {day}: {len(bp_df)} docks, {len(ls_df)} line-statuses "
          f"({disrupted} not good service)")


if __name__ == "__main__":
    main()
