"""Read-only MCP server over the TfL gold layer (durable, warehouse-free).

An AI-integration DEMONSTRATION on top of the pipeline, not pipeline machinery — it exposes the
gold layer to an AI client (e.g. Claude Desktop) through a few curated, typed tools.

Durable by design (see docs/adr/ADR-0004-mcp-readonly-boundary.md): it queries the **committed
gold Parquet** (`app/gold_export/`) via DuckDB — the same trial-independent source the Streamlit
app uses — so it keeps working after the Snowflake trial ends, with no credentials.

Guardrails preserved:
- **Read-only by construction.** DuckDB opens the Parquet read-only; there is no write path and
  no access to raw/silver — only the curated gold rollups exposed below.
- **Curated, typed tools with bind parameters — never free-form SQL.** The LLM calls a named tool
  or gets nothing; it cannot inject SQL or reach tables that aren't exposed here.
"""

from datetime import datetime
from pathlib import Path
import logging

import duckdb
from mcp.server.fastmcp import FastMCP

# Keep stdout clean for the MCP JSON-RPC stream.
logging.getLogger("duckdb").setLevel(logging.WARNING)

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "app" / "gold_export"

mcp = FastMCP("tfl-gold")


def _query(sql: str, params: tuple = ()) -> list[dict]:
    """Run one parameterized query over the committed gold Parquet (read-only) and return rows.

    Views expose only the three gold rollups the tools need — the LLM cannot reach anything else.
    """
    con = duckdb.connect()  # fresh in-memory connection; Parquet opened read-only
    try:
        con.execute(
            f"""
            create view dim_station as select * from read_parquet('{(EXPORT / "dim_station.parquet").as_posix()}');
            create view station_daily_flows as select * from read_parquet('{(EXPORT / "station_daily_flows.parquet").as_posix()}');
            create view daily_journey_stats as select * from read_parquet('{(EXPORT / "daily_journey_stats.parquet").as_posix()}');
            """
        )
        res = con.execute(sql, list(params))
        cols = [c[0].lower() for c in res.description]
        return [dict(zip(cols, row)) for row in res.fetchall()]
    finally:
        con.close()


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
        from dim_station
        where station_name ilike ?
        order by dock_events desc
        limit ?
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
        select station_name,
               sum(departures) as departures,
               sum(arrivals)   as arrivals
        from station_daily_flows
        where date_key between ? and ?
        group by station_name
        order by sum({metric}) desc
        limit ?
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
        select cast(date_day as varchar) as date_day, journeys, avg_duration_min, ebike_journeys
        from daily_journey_stats
        where date_key between ? and ?
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
        select date_key, station_name, departures, arrivals, net_inflow
        from station_daily_flows
        where station_name = ? and date_key between ? and ?
        order by date_key
        """,
        (station_name, _date_key(start_date), _date_key(end_date)),
    )


def _date_key(d: str) -> int:
    """YYYY-MM-DD -> YYYYMMDD integer (the gold date_key). Validates format."""
    return int(datetime.strptime(d.strip(), "%Y-%m-%d").strftime("%Y%m%d"))


if __name__ == "__main__":
    mcp.run()
