"""Export an HOURLY station rollup from Snowflake before the trial expires.

The committed gold layer is daily-grain (station_daily_flows). The hourly grain exists only in
TFL.GOLD.FACT_JOURNEY, which dies with the Snowflake trial — after that, recovering hours means
re-running the full Spark backfill. This one-time export banks station × date × hour departures/
arrivals as committed Parquet, keeping an hourly event-study possible later (rigor-pass C2 ruling:
insurance only; v1 analysis stays daily).

Writes app/gold_export/hourly/station_hourly_<year>.parquet (one file per year, compact dtypes,
each well under GitHub's limits). Read-only; idempotent (overwrites per-year files).

Run once while the trial is live:  .venv/Scripts/python ingestion/export_hourly_rollup.py
"""

import os
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
OUT_DIR = ROOT / "app" / "gold_export" / "hourly"

SQL = """
with dep as (
    select start_station_key                       as station_key,
           start_date_key                          as date_key,
           hour(start_ts)                          as hour_of_day,
           count(*)                                as departures
    from TFL.GOLD.FACT_JOURNEY
    where start_station_key is not null
      and start_ts is not null
      and start_date_key between %(lo)s and %(hi)s
    group by 1, 2, 3
),
arr as (
    select end_station_key                          as station_key,
           to_number(to_char(end_ts, 'YYYYMMDD'))   as date_key,
           hour(end_ts)                             as hour_of_day,
           count(*)                                 as arrivals
    from TFL.GOLD.FACT_JOURNEY
    where end_station_key is not null
      and end_ts is not null
      and to_number(to_char(end_ts, 'YYYYMMDD')) between %(lo)s and %(hi)s
    group by 1, 2, 3
)
select coalesce(d.station_key, a.station_key)   as station_key,
       coalesce(d.date_key, a.date_key)         as date_key,
       coalesce(d.hour_of_day, a.hour_of_day)   as hour_of_day,
       coalesce(d.departures, 0)                as departures,
       coalesce(a.arrivals, 0)                  as arrivals
from dep d
full outer join arr a
  on d.station_key = a.station_key
 and d.date_key    = a.date_key
 and d.hour_of_day = a.hour_of_day
"""


def main() -> None:
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.getenv("SNOWFLAKE_ROLE") or "ACCOUNTADMIN",
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE") or "TFL_WH",
        database=os.getenv("SNOWFLAKE_DATABASE") or "TFL",
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total_rows = total_dep = 0
    try:
        cur = conn.cursor()
        for year in range(2021, 2027):
            cur.execute(SQL, {"lo": year * 10000 + 101, "hi": year * 10000 + 1231})
            df = cur.fetch_pandas_all()
            if df.empty:
                print(f"{year}: no rows, skipped")
                continue
            df.columns = [c.lower() for c in df.columns]
            df = df.astype({
                "date_key": "int32", "hour_of_day": "int8",
                "departures": "int16", "arrivals": "int16",
            }).sort_values(["station_key", "date_key", "hour_of_day"])
            path = OUT_DIR / f"station_hourly_{year}.parquet"
            df.to_parquet(path, index=False, compression="zstd")
            mb = path.stat().st_size / 1e6
            total_rows += len(df)
            total_dep += int(df["departures"].sum())
            print(f"{year}: {len(df):,} rows, {int(df['departures'].sum()):,} departures "
                  f"-> {path.name} ({mb:.1f} MB)")
            if mb > 90:
                raise SystemExit(f"{path.name} is {mb:.0f} MB — over the 90 MB budget; re-shard.")
    finally:
        conn.close()
    print(f"\nTOTAL: {total_rows:,} station-hour rows; {total_dep:,} departures "
          f"(expect ≈ journeys with valid start station/ts, ~41M)")


if __name__ == "__main__":
    main()
