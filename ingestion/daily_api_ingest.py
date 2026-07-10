"""Daily incremental pull: TfL BikePoint + Line Status -> Snowflake.

Deliberately plain Python (the other side of the Spark honesty boundary): one
day's snapshot is ~800 dock rows + ~20 line rows. Raw JSON lands as-pulled in
data/raw/api/<date>/ (bronze), typed rows go to TFL.SILVER via delete+insert on
snapshot_date, so re-runs for the same day are idempotent.

Works keyless (TfL allows low-rate anonymous calls); uses TFL_APP_KEY when set.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import snowflake.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.tfl.gov.uk"
RAIL_MODES = "tube,dlr,overground,elizabeth-line,tram"

BIKEPOINT_DDL = """
create table if not exists TFL.SILVER.BIKEPOINT_SNAPSHOT (
    snapshot_date date,
    pulled_at timestamp_ntz,
    bikepoint_id varchar,
    common_name varchar,
    lat float,
    lon float,
    installed boolean,
    locked boolean,
    n_docks integer,
    n_bikes integer,
    n_empty_docks integer,
    n_ebikes integer
)
"""
LINE_STATUS_DDL = """
create table if not exists TFL.SILVER.LINE_STATUS_SNAPSHOT (
    snapshot_date date,
    pulled_at timestamp_ntz,
    line_id varchar,
    line_name varchar,
    mode varchar,
    status_severity integer,
    status_description varchar,
    disruption_reason varchar
)
"""


def prop(place: dict, key: str):
    for p in place.get("additionalProperties", []):
        if p.get("key") == key:
            return p.get("value")
    return None


def pull(session: requests.Session, path: str, params: dict) -> list:
    resp = session.get(f"{API}{path}", params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat())
    args = parser.parse_args()
    snapshot_date = args.date
    pulled_at = datetime.now(timezone.utc).replace(tzinfo=None)

    load_dotenv(ROOT / ".env")
    params = {"app_key": os.environ["TFL_APP_KEY"]} if os.getenv("TFL_APP_KEY") else {}

    session = requests.Session()
    bikepoints = pull(session, "/BikePoint", params)
    lines = pull(session, f"/Line/Mode/{RAIL_MODES}/Status", params)

    # bronze: land raw JSON exactly as pulled
    raw_dir = ROOT / "data" / "raw" / "api" / snapshot_date
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "bikepoint.json").write_text(json.dumps(bikepoints), encoding="utf-8")
    (raw_dir / "line_status.json").write_text(json.dumps(lines), encoding="utf-8")

    # ingestion quality gates: a partial API response should fail loudly,
    # not load a half-empty snapshot
    if len(bikepoints) < 700:
        sys.exit(f"quality gate: only {len(bikepoints)} bikepoints (expected ~800)")
    if len(lines) < 15:
        sys.exit(f"quality gate: only {len(lines)} lines (expected ~20)")

    def as_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    bp_rows = [
        (
            snapshot_date, pulled_at, p.get("id"), p.get("commonName"),
            p.get("lat"), p.get("lon"),
            prop(p, "Installed") == "true", prop(p, "Locked") == "true",
            as_int(prop(p, "NbDocks")), as_int(prop(p, "NbBikes")),
            as_int(prop(p, "NbEmptyDocks")), as_int(prop(p, "NbEBikes")),
        )
        for p in bikepoints
    ]
    ls_rows = []
    for ln in lines:
        for st in ln.get("lineStatuses", [{}]):
            ls_rows.append(
                (
                    snapshot_date, pulled_at, ln.get("id"), ln.get("name"),
                    ln.get("modeName"), st.get("statusSeverity"),
                    st.get("statusSeverityDescription"), st.get("reason"),
                )
            )

    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse="TFL_WH",
    )
    cur = conn.cursor()
    cur.execute(BIKEPOINT_DDL)
    cur.execute(LINE_STATUS_DDL)
    for table, rows, width in [
        ("TFL.SILVER.BIKEPOINT_SNAPSHOT", bp_rows, 12),
        ("TFL.SILVER.LINE_STATUS_SNAPSHOT", ls_rows, 8),
    ]:
        cur.execute(f"delete from {table} where snapshot_date = %s", (snapshot_date,))
        placeholders = ", ".join(["%s"] * width)
        cur.executemany(f"insert into {table} values ({placeholders})", rows)
        cur.execute(f"select count(*) from {table} where snapshot_date = %s", (snapshot_date,))
        print(f"{table}: {cur.fetchone()[0]} rows for {snapshot_date}")
    conn.close()


if __name__ == "__main__":
    main()
