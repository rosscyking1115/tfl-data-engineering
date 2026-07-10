"""Phase 0 insurance: capture a compact station demand baseline from Snowflake
BEFORE the trial suspends (~2026-08-06), so the durable workflow never needs the
warehouse again.

Exports a station x day-of-week x hour departure profile (avg via departures/n_days).
Tiny (<= 856 stations x 7 x 24 rows), committed to app/gold_export/.
"""

import os
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "gold_export"

PROFILE_SQL = """
select
    s.station_name,
    dayofweekiso(f.start_ts)        as dow_iso,
    hour(f.start_ts)                as hour_of_day,
    count(*)                        as departures,
    count(distinct to_date(f.start_ts)) as n_days,
    round(count(*) / nullif(count(distinct to_date(f.start_ts)), 0), 3) as avg_departures
from TFL.GOLD.FACT_JOURNEY f
join TFL.GOLD.DIM_STATION s on f.start_station_key = s.station_key
group by 1, 2, 3
"""


def main() -> None:
    load_dotenv(ROOT / ".env")
    OUT.mkdir(parents=True, exist_ok=True)
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse="TFL_WH",
        database="TFL",
        schema="GOLD",
    )
    cur = conn.cursor()
    cur.execute(PROFILE_SQL)
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    target = OUT / "station_hourofweek_profile.parquet"
    df.to_parquet(target, index=False)
    conn.close()
    print(f"[OK] station_hourofweek_profile: {len(df):,} rows "
          f"({df['station_name'].nunique()} stations) -> {target.name} "
          f"({target.stat().st_size/1e6:.2f} MB)")


if __name__ == "__main__":
    main()
