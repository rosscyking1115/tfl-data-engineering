"""Station footfall increment: daily rail entry/exit tap counts from TfL's crowding bucket.

TfL publishes daily per-station tap counts to crowding.data.tfl.gov.uk as StationFootfall_*.csv.
Unlike the journey extracts (published in bulk with a ~1-2 month lag), this series is refreshed
every few days: verified 2026-07-27, the current file was modified 2026-07-22 and carried data
through 2026-07-18 — a four-day lag.

WHAT THIS IS NOT. Tap counts are gate entries and exits on the *rail* network. They are not
journeys, and they are not the cycle-hire population. Nothing here joins to dim_station, so the
column is named `rail_station` to keep an accidental join visibly wrong. This is a context
series for the live layer, not evidence about cycling demand (see docs/source_contracts.md).

Source quirks, all verified 2026-07-27 and handled by name rather than position:
  * Header case drifts: 2019-2022 spell the column `DayOFWeek`, 2023 onward `DayOfWeek`.
  * 2019-2023 files carry a UTF-8 BOM; 2024 onward do not.
  * The two rolling files have a literal SPACE before `.csv` in their key.
  * The files OVERLAP: StationFootfall_2024_2025 spans 20240101-20251227, fully containing
    StationFootfall_2024 and half of the 2025_2026 file. Concatenating everything would
    double-count two whole years. BACKFILL_KEYS is therefore an explicitly non-overlapping
    set, and the (date_key, rail_station) upsert makes a mistake here idempotent rather than
    additive. Where the files do overlap they agree exactly (156,995 rows compared for 2024,
    zero disagreements), so dropping the redundant file loses nothing.

Behaviour:
  * Default: fetch only the current rolling file and upsert it — a few MB, the weekly path.
  * --backfill: fetch the full non-overlapping set and rebuild from scratch.
  * Schema gate: the required columns must all be present after case-normalisation, or the
    run FAILS LOUDLY rather than mis-parsing (same contract as journey_increment.py).

Run:  .venv/Scripts/python ingestion/station_footfall.py [--backfill]
"""

from __future__ import annotations

import argparse
import io
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "app" / "gold_export"
OUT = EXPORT / "station_footfall.parquet"

BUCKET = "https://crowding.data.tfl.gov.uk/Network%20Demand/"

# The current rolling file: re-published every few days, covers 2025-01-01 onward.
CURRENT_KEY = "StationFootfall_2025_2026 .csv"

# Deliberately NON-OVERLAPPING. StationFootfall_2024_2025 is omitted because
# StationFootfall_2024 + the current rolling file already cover its whole span.
BACKFILL_KEYS = [
    "StationFootfall_2019.csv",
    "StationFootfall_2020.csv",
    "StationFootfall_2021.csv",
    "StationFootfall_2022.csv",
    "StationFootfall_2023.csv",
    "StationFootfall_2024.csv",
    CURRENT_KEY,
]

# Source contract. Keys are lowercase so the DayOFWeek/DayOfWeek drift cannot break the gate.
REQUIRED_COLUMNS = {
    "traveldate": "date_key",
    "dayofweek": "day_of_week",
    "station": "rail_station",
    "entrytapcount": "entry_taps",
    "exittapcount": "exit_taps",
}


def fetch(key: str) -> pd.DataFrame:
    """Download one StationFootfall file and normalise it to the internal contract."""
    resp = requests.get(BUCKET + key.replace(" ", "%20"), timeout=300)
    resp.raise_for_status()
    # utf-8-sig strips the BOM the pre-2024 files carry; without it the first column name
    # arrives as "﻿TravelDate" and the schema gate would fire on a cosmetic difference.
    raw = pd.read_csv(io.BytesIO(resp.content), encoding="utf-8-sig")

    lookup = {c.strip().lower(): c for c in raw.columns}
    missing = [want for want in REQUIRED_COLUMNS if want not in lookup]
    if missing:
        raise SystemExit(
            f"schema gate: {key} is missing {missing}; got {list(raw.columns)}. "
            "TfL drifted the footfall format — fix the mapping rather than guessing positions."
        )
    df = raw[[lookup[want] for want in REQUIRED_COLUMNS]]
    df.columns = list(REQUIRED_COLUMNS.values())
    return df


def check_quality(df: pd.DataFrame) -> None:
    """Fail loudly on an empty, negative or duplicated series rather than committing it."""
    if df.empty:
        raise SystemExit("quality gate: no footfall rows")
    if (df["entry_taps"] < 0).any() or (df["exit_taps"] < 0).any():
        raise SystemExit("quality gate: negative tap counts")
    dupes = int(df.duplicated(["date_key", "rail_station"]).sum())
    if dupes:
        raise SystemExit(f"quality gate: {dupes} duplicate (date_key, rail_station) rows")


def upsert(new: pd.DataFrame) -> pd.DataFrame:
    """Replace every date_key present in `new`, then append — idempotent, so re-running the
    weekly fetch corrects a revised day instead of double-counting it."""
    if not OUT.exists():
        return new
    prev = pd.read_parquet(OUT)
    prev = prev[~prev["date_key"].isin(new["date_key"].unique())]
    return pd.concat([prev, new], ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backfill", action="store_true",
                        help="rebuild the whole series from the non-overlapping file set")
    args = parser.parse_args()

    keys = BACKFILL_KEYS if args.backfill else [CURRENT_KEY]
    fetched = pd.concat([fetch(k) for k in keys], ignore_index=True)
    # Records when THIS run landed these rows, so `dbt source freshness` can measure the
    # real refresh lag rather than us asserting a cadence. Historical rows keep the
    # pulled_at of the run that last carried them.
    fetched["pulled_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"fetched {len(fetched):,} rows from {len(keys)} file(s)")

    df = fetched if args.backfill else upsert(fetched)
    df = df.astype({"date_key": "int64", "entry_taps": "int64", "exit_taps": "int64"})
    df = df.sort_values(["date_key", "rail_station"]).reset_index(drop=True)
    check_quality(df)

    EXPORT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False, compression="zstd")
    print(
        f"wrote {OUT.relative_to(ROOT)}: {len(df):,} rows, "
        f"{df['date_key'].min()}..{df['date_key'].max()}, "
        f"{df['rail_station'].nunique()} stations, {OUT.stat().st_size / 1e6:.2f} MB"
    )


if __name__ == "__main__":
    main()
