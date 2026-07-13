"""Daily journey-CSV increment: keep the committed gold Parquet current as TfL publishes.

TfL publishes journey extracts to the open bucket (usage-stats/NNNJourneyDataExtract...csv)
every ~2 weeks, with a 1-2 month lag. The Spark backfill built the deep history once; this is
the deliberately-light forward path (rigor-pass Area 5 / plans' "ingestion path 2"): pure
Python + DuckDB, because a single extract is a few hundred thousand rows — Spark here would
be theatre (ADR-0003).

Behaviour:
  * Lists the bucket, parses extract numbers/end-dates from filenames, and ingests anything
    newer than the committed state (app/gold_export/journey_ingest_state.json).
  * Schema gate: the nextgen columns must all be present — a renamed column means TfL drifted
    the format again, and the run FAILS LOUDLY rather than mis-parsing (source-contract tripwire).
  * Aggregates to the two committed rollups (station_daily_flows, daily_journey_stats) and
    REPLACES the affected date_keys — idempotent, and a fuller re-publish of a boundary day
    (e.g. the partial 2026-06-01 spill in extract 444) is corrected, not double-counted.
  * station_key = md5(whitespace-collapsed station name) — verified identical to the
    dbt_utils surrogate key in the committed dim (so new rows join the existing star schema).
  * Refreshes weather_daily forward (one cheap full-range Open-Meteo call).

Known, documented approximation: arrivals on a file-boundary date can miss rides that STARTED
in the previous extract and docked on that date (departures — the demand measure — are exact,
because extracts are windowed by start date). The full-accuracy path is the Spark backfill.

Run:  .venv/Scripts/python ingestion/journey_increment.py   (no args; no-op when up to date)
"""

from __future__ import annotations

import json
import re
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "app" / "gold_export"
STATE_PATH = EXPORT / "journey_ingest_state.json"

BUCKET = "https://s3-eu-west-1.amazonaws.com/cycling.data.tfl.gov.uk/"
KEY_RE = re.compile(r"usage-stats/(\d+)JourneyDataExtract(\d{2}\w{3}\d{4})-(\d{2}\w{3}\d{4})\.csv$")

# The nextgen source contract: every column the increment depends on. A missing name =
# schema drift = loud failure (never positional guessing — the backfill's hard lesson).
REQUIRED_COLUMNS = [
    "Number", "Start date", "End date", "Bike number", "Bike model",
    "Total duration (ms)", "Start station number", "Start station",
    "End station number", "End station",
]


# ------------------------------------------------------------------- state & listing

def load_state() -> dict:
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def parse_key(key: str) -> dict | None:
    m = KEY_RE.search(key)
    if not m:
        return None
    return {
        "key": key,
        "extract": int(m.group(1)),
        "start": datetime.strptime(m.group(2), "%d%b%Y").date().isoformat(),
        "end": datetime.strptime(m.group(3), "%d%b%Y").date().isoformat(),
    }


def list_new_files(state: dict, session: requests.Session | None = None) -> list[dict]:
    s = session or requests.Session()
    r = s.get(BUCKET, params={"list-type": "2", "prefix": "usage-stats/", "max-keys": "1000"},
              timeout=120)
    r.raise_for_status()
    ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
    keys = [c.find(ns + "Key").text for c in ET.fromstring(r.content).findall(ns + "Contents")]
    parsed = [p for k in keys if (p := parse_key(k))]
    new = [p for p in parsed if p["extract"] > state["max_extract"]]
    return sorted(new, key=lambda p: p["extract"])


# ------------------------------------------------------------------- parse & aggregate

def aggregate_file(csv_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One extract -> (station_daily_flows rows, daily_journey_stats rows).

    Pure function over a local CSV (unit-tested on fixtures). Applies the same cleaning the
    dbt staging layer applies to the backfill: whitespace-collapsed names, per-file dedupe
    on the rental Number, md5(name) station keys.
    """
    con = duckdb.connect()
    try:
        cols = {r[0] for r in con.execute(
            f"describe select * from read_csv_auto('{csv_path.as_posix()}', header=true)"
        ).fetchall()}
        missing = [c for c in REQUIRED_COLUMNS if c not in cols]
        if missing:
            raise SystemExit(
                f"schema gate: {csv_path.name} is missing expected column(s) {missing} — "
                "TfL format drift; refusing to guess (update the contract + this loader)."
            )

        base = f"""
        with raw as (
            select *, row_number() over (partition by "Number" order by "Start date") as rn
            from read_csv_auto('{csv_path.as_posix()}', header=true)
            where "Number" is not null and "Start date" is not null
        ),
        j as (
            select
                regexp_replace(trim("Start station"), '\\s+', ' ', 'g')  as start_name,
                regexp_replace(trim("End station"),   '\\s+', ' ', 'g')  as end_name,
                cast("Start date" as timestamp)                           as start_ts,
                cast("End date" as timestamp)                             as end_ts,
                cast("Total duration (ms)" as bigint) / 1000              as duration_s,
                "Bike number"                                             as bike_id,
                "Bike model"                                              as bike_model
            from raw where rn = 1
        )
        """

        flows = con.execute(base + """
        , dep as (
            select md5(start_name) as station_key, start_name as station_name,
                   cast(strftime(start_ts, '%Y%m%d') as integer) as date_key,
                   count(*) as departures
            from j where start_name is not null and start_name <> '' group by 1, 2, 3
        ),
        arr as (
            select md5(end_name) as station_key, end_name as station_name,
                   cast(strftime(end_ts, '%Y%m%d') as integer) as date_key,
                   count(*) as arrivals
            from j where end_name is not null and end_name <> '' and end_ts is not null
            group by 1, 2, 3
        )
        select coalesce(d.date_key, a.date_key)              as date_key,
               coalesce(d.station_key, a.station_key)        as station_key,
               coalesce(d.station_name, a.station_name)      as station_name,
               coalesce(d.departures, 0)                     as departures,
               coalesce(a.arrivals, 0)                       as arrivals,
               coalesce(a.arrivals, 0) - coalesce(d.departures, 0) as net_inflow
        from dep d full outer join arr a using (station_key, date_key)
        """).df()

        daily = con.execute(base + """
        select
            cast(strftime(start_ts, '%Y%m%d') as integer)      as date_key,
            cast(start_ts as date)                             as date_day,
            count(*)                                           as journeys,
            round(avg(duration_s) / 60, 2)                     as avg_duration_min,
            round(median(duration_s) / 60, 2)                  as median_duration_min,
            count(distinct bike_id)                            as distinct_bikes,
            sum(case when bike_model = 'PBSC_EBIKE' then 1 else 0 end) as ebike_journeys
        from j group by 1, 2
        """).df()
    finally:
        con.close()

    if not (1_000 <= int(daily["journeys"].sum()) <= 3_000_000):
        raise SystemExit(f"quality gate: {csv_path.name} has {int(daily['journeys'].sum()):,} "
                         "journeys — outside plausible bounds for one extract.")
    # internal reconciliation: flows departures must equal daily journeys exactly
    if int(flows["departures"].sum()) != int(daily["journeys"].sum()):
        raise SystemExit("reconciliation gate: departures != journeys within the extract.")
    return flows, daily


def replace_dates(parquet_path: Path, new_rows: pd.DataFrame, date_keys: list[int]) -> None:
    """Idempotent date-level upsert into a committed rollup parquet: drop the affected
    date_keys, append the recomputed rows. Preserves column order/dtypes of the target."""
    existing = pd.read_parquet(parquet_path)
    kept = existing[~existing["date_key"].isin(date_keys)]
    aligned = new_rows.reindex(columns=existing.columns)
    for col in existing.columns:  # keep committed dtypes stable (int16 counts etc.)
        try:
            aligned[col] = aligned[col].astype(existing[col].dtype)
        except (TypeError, ValueError):
            pass
    out = pd.concat([kept, aligned], ignore_index=True).sort_values(
        [c for c in ("date_key", "station_key") if c in existing.columns])
    out.to_parquet(parquet_path, index=False)


# ------------------------------------------------------------------------------ main

def main() -> None:
    state = load_state()
    session = requests.Session()
    new = list_new_files(state, session)
    if not new:
        print(f"[OK] journey data up to date (through extract {state['max_extract']}, "
              f"{state['max_end_date']}); nothing to ingest.")
        return

    for meta in new:
        print(f"ingesting extract {meta['extract']} ({meta['start']} -> {meta['end']}) ...")
        with tempfile.TemporaryDirectory() as td:
            local = Path(td) / "extract.csv"
            with session.get(BUCKET + meta["key"], timeout=600, stream=True) as r:
                r.raise_for_status()
                local.write_bytes(r.content)
            flows, daily = aggregate_file(local)

        dates = sorted(daily["date_key"].unique().tolist())
        replace_dates(EXPORT / "station_daily_flows.parquet", flows,
                      sorted(flows["date_key"].unique().tolist()))
        replace_dates(EXPORT / "daily_journey_stats.parquet", daily, dates)
        state["max_extract"] = meta["extract"]
        state["max_end_date"] = meta["end"]
        state.setdefault("ingested", []).append(meta["key"])
        save_state(state)
        print(f"  {int(daily['journeys'].sum()):,} journeys over {len(dates)} days upserted; "
              f"state -> extract {meta['extract']}")

    # forward weather so the deviation baseline can bucket the new dates
    import weather  # local module (same folder)

    end = datetime.now(timezone.utc).date().isoformat()
    df = weather.fetch("2021-12-01", end)
    df.to_parquet(EXPORT / "weather_daily.parquet", index=False)
    print(f"[OK] weather refreshed through {end} ({len(df):,} days)")


if __name__ == "__main__":
    main()
