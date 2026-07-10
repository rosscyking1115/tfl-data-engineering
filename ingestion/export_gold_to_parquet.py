"""Export gold rollups + dimensions from Snowflake to local Parquet.

Two purposes:
1. Trial-independence — the Snowflake trial suspends ~2026-08-06, after which queries
   are blocked. These Parquet files let the Streamlit demo (app/) keep working forever
   with no live warehouse. RUN THIS BEFORE THE TRIAL SUSPENDS.
2. Free hosting — Streamlit Community Cloud reads the committed Parquet via DuckDB.

Exports the import-friendly gold models only. fact_journey (41M rows) is deliberately
excluded — too big for GitHub; the rollups exist precisely so BI never touches it.
"""

import os
from pathlib import Path

import pandas as pd
import snowflake.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "gold_export"

# gold table -> output parquet name. Row counts are asserted against the live table.
TABLES = ["DAILY_JOURNEY_STATS", "STATION_DAILY_FLOWS", "DIM_STATION", "DIM_DATE"]


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
    for table in TABLES:
        cur.execute(f"select count(*) from TFL.GOLD.{table}")
        expected = cur.fetchone()[0]
        cur.execute(f"select * from TFL.GOLD.{table}")
        df = cur.fetch_pandas_all()
        df.columns = [c.lower() for c in df.columns]
        target = OUT / f"{table.lower()}.parquet"
        df.to_parquet(target, index=False)
        got = len(pd.read_parquet(target))
        status = "OK" if got == expected == len(df) else "MISMATCH"
        print(f"[{status}] {table}: gold={expected:,} parquet={got:,} "
              f"({target.stat().st_size/1e6:.1f} MB)")
        assert got == expected, f"row-count mismatch for {table}"
    conn.close()
    print(f"exported {len(TABLES)} tables -> {OUT}")


if __name__ == "__main__":
    main()
