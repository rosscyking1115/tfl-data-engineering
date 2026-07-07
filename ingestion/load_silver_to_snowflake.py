"""Load local silver parquet into Snowflake via internal stage + COPY INTO.

Prereq: Snowflake trial account, credentials in .env (see .env.example).
Idempotent: objects are CREATE IF NOT EXISTS and COPY INTO skips files already
loaded (Snowflake load metadata), so re-runs only ship new partitions.

The warehouse is XSMALL with AUTO_SUSPEND=60 — the cost story in the README
depends on keeping this honest.
"""

from pathlib import Path
import os
import sys

from dotenv import load_dotenv
import snowflake.connector

ROOT = Path(__file__).resolve().parents[1]
SILVER = ROOT / "data" / "silver" / "journeys"

DDL = [
    "create warehouse if not exists TFL_WH warehouse_size=XSMALL auto_suspend=60 "
    "auto_resume=true initially_suspended=true",
    "create database if not exists TFL",
    "create schema if not exists TFL.SILVER",
    """
    create table if not exists TFL.SILVER.JOURNEYS (
        era varchar,
        rental_id bigint,
        bike_id bigint,
        bike_model varchar,
        start_ts timestamp_ntz,
        end_ts timestamp_ntz,
        duration_s bigint,
        start_station_code varchar,
        start_station_name varchar,
        end_station_code varchar,
        end_station_name varchar,
        source_file varchar,
        ingested_at timestamp_ntz
    )
    """,
    "create file format if not exists TFL.SILVER.PQ type=parquet",
    "create stage if not exists TFL.SILVER.JOURNEYS_STAGE file_format=TFL.SILVER.PQ",
]


def main() -> None:
    load_dotenv(ROOT / ".env")
    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)} — sign up at signup.snowflake.com and fill .env")

    parquet_dirs = sorted({p.parent for p in SILVER.rglob("*.parquet")})
    if not parquet_dirs:
        sys.exit(f"No parquet under {SILVER} — run the backfill first (infra/run_backfill.ps1)")

    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.getenv("SNOWFLAKE_ROLE") or None,
    )
    cur = conn.cursor()
    for stmt in DDL:
        cur.execute(stmt)
    cur.execute("use warehouse TFL_WH")
    cur.execute("use schema TFL.SILVER")

    for d in parquet_dirs:
        # keep the year=/month= partition path inside the stage for traceability
        rel = d.relative_to(SILVER).as_posix()
        cur.execute(
            f"put 'file://{d.as_posix()}/*.parquet' @JOURNEYS_STAGE/{rel}/ "
            "auto_compress=false parallel=8"
        )
        print(f"staged {rel}")

    cur.execute(
        "copy into JOURNEYS from @JOURNEYS_STAGE "
        "match_by_column_name=case_insensitive file_format=(type=parquet)"
    )
    loaded = cur.fetchall()
    print(f"COPY INTO: {len(loaded)} staged files processed")

    cur.execute("select era, count(*), min(start_ts), max(start_ts) from JOURNEYS group by era")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,} rows ({row[2]} -> {row[3]})")
    cur.execute("select count(*) from JOURNEYS")
    print(f"TOTAL in Snowflake: {cur.fetchone()[0]:,}")
    conn.close()


if __name__ == "__main__":
    main()
