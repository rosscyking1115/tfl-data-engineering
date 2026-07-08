"""Phase 5 (bonus): read-only MCP server over the TfL gold layer.

An AI-integration DEMONSTRATION on top of the pipeline, not pipeline machinery
(Airflow orchestrates the pipeline; this just exposes gold to an AI client).

Design guardrails (see docs/adr/ADR-0004-mcp-readonly-boundary.md):
- Connects as TFL_GOLD_READONLY and runs `use secondary roles none`, so ACCOUNTADMIN
  cannot leak in through the trial account's default secondary roles. The role can
  only SELECT TFL.GOLD — it cannot write, and cannot read SILVER/RAW.
- Exposes a few CURATED, typed tools with bind parameters — never free-form SQL.
  The LLM calls a tool or gets nothing; it cannot guess table names or inject SQL.
"""

from pathlib import Path
import logging
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
import snowflake.connector

# Keep stdout clean for the MCP JSON-RPC stream; silence the connector's chatter.
logging.getLogger("snowflake.connector").setLevel(logging.WARNING)

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

mcp = FastMCP("tfl-gold")


def _query(sql: str, params: tuple = ()) -> list[dict]:
    """Open a short-lived read-only connection, run one parameterized query, return rows."""
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.getenv("SNOWFLAKE_MCP_ROLE", "TFL_GOLD_READONLY"),
        warehouse="TFL_WH",
        database="TFL",
        schema="GOLD",
    )
    try:
        cur = conn.cursor()
        cur.execute("use secondary roles none")  # critical: no privilege leakage
        cur.execute(sql, params)
        cols = [c[0].lower() for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


@mcp.tool()
def search_stations(name_substring: str, limit: int = 20) -> list[dict]:
    """Find cycle-hire stations whose name contains the given text (case-insensitive).

    Use this first to resolve a human station name to its exact name before calling
    station_flow. Returns station_name and the two era-specific IDs.
    """
    limit = max(1, min(int(limit), 100))
    return _query(
        """
        select station_name, classic_station_id, nextgen_station_code, dock_events
        from TFL.GOLD.DIM_STATION
        where station_name ilike %s
        order by dock_events desc
        limit %s
        """,
        (f"%{name_substring}%", limit),
    )


@mcp.tool()
def top_stations(start_date: str, end_date: str, by: str = "departures", limit: int = 10) -> list[dict]:
    """Rank the busiest stations between two dates (inclusive, YYYY-MM-DD).

    `by` is 'departures' or 'arrivals'. Returns station_name with total departures
    and arrivals over the window.
    """
    metric = "departures" if by != "arrivals" else "arrivals"
    limit = max(1, min(int(limit), 100))
    return _query(
        f"""
        select d.station_name,
               sum(f.departures) as departures,
               sum(f.arrivals)   as arrivals
        from TFL.GOLD.STATION_DAILY_FLOWS f
        join TFL.GOLD.DIM_STATION d on f.station_key = d.station_key
        where f.date_key between %s and %s
        group by d.station_name
        order by sum(f.{metric}) desc
        limit %s
        """,
        (_date_key(start_date), _date_key(end_date), limit),
    )


@mcp.tool()
def daily_usage_trend(start_date: str, end_date: str) -> list[dict]:
    """System-wide daily usage between two dates (inclusive, YYYY-MM-DD).

    Returns one row per day: total journeys, average duration (min), and e-bike journeys.
    """
    return _query(
        """
        select date_day, journeys, avg_duration_min, ebike_journeys
        from TFL.GOLD.DAILY_JOURNEY_STATS
        where date_key between %s and %s
        order by date_day
        """,
        (_date_key(start_date), _date_key(end_date)),
    )


@mcp.tool()
def station_flow(station_name: str, start_date: str, end_date: str) -> list[dict]:
    """Daily departures, arrivals and net inflow for ONE station over a date window.

    `station_name` must match a dim_station name exactly — call search_stations first
    if unsure. Dates are inclusive YYYY-MM-DD. net_inflow = arrivals - departures.
    """
    return _query(
        """
        select f.date_key, d.station_name, f.departures, f.arrivals, f.net_inflow
        from TFL.GOLD.STATION_DAILY_FLOWS f
        join TFL.GOLD.DIM_STATION d on f.station_key = d.station_key
        where d.station_name = %s and f.date_key between %s and %s
        order by f.date_key
        """,
        (station_name, _date_key(start_date), _date_key(end_date)),
    )


def _date_key(d: str) -> int:
    """YYYY-MM-DD -> YYYYMMDD integer (the gold date_key). Validates format."""
    from datetime import datetime

    return int(datetime.strptime(d.strip(), "%Y-%m-%d").strftime("%Y%m%d"))


if __name__ == "__main__":
    mcp.run()
