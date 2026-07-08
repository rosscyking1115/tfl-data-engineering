"""Read-only data access for the Streamlit demo.

Queries the committed gold Parquet (app/gold_export/) via DuckDB — no live Snowflake
connection, so the demo works forever and hosts free on Streamlit Community Cloud.
All loaders are cached; the Parquet is small (rollups + dims, ~9 MB).
"""

from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

EXPORT = Path(__file__).resolve().parent / "gold_export"


def _q(sql: str, params: list | None = None) -> pd.DataFrame:
    con = duckdb.connect()  # fresh in-memory con per call; parquet opened read-only
    try:
        con.execute(
            f"""
            create view daily as select * from read_parquet('{(EXPORT / "daily_journey_stats.parquet").as_posix()}');
            create view flows as select * from read_parquet('{(EXPORT / "station_daily_flows.parquet").as_posix()}');
            create view stations as select * from read_parquet('{(EXPORT / "dim_station.parquet").as_posix()}');
            """
        )
        return con.execute(sql, params or []).df()
    finally:
        con.close()


@st.cache_data(ttl="1h")
def daily_stats() -> pd.DataFrame:
    return _q("select * from daily order by date_day")


@st.cache_data(ttl="1h")
def date_bounds() -> tuple:
    row = _q("select min(date_day) lo, max(date_day) hi from daily").iloc[0]
    return row["lo"], row["hi"]


@st.cache_data(ttl="1h")
def station_names() -> list[str]:
    return _q("select station_name from stations order by station_name")["station_name"].tolist()


@st.cache_data(ttl="1h")
def top_stations(start: str, end: str, by: str, limit: int) -> pd.DataFrame:
    metric = "arrivals" if by == "arrivals" else "departures"
    return _q(
        f"""
        select s.station_name,
               sum(f.departures) as departures,
               sum(f.arrivals)   as arrivals
        from flows f join stations s on f.station_key = s.station_key
        where f.date_key between ? and ?
        group by s.station_name
        order by sum(f.{metric}) desc
        limit ?
        """,
        [_key(start), _key(end), limit],
    )


@st.cache_data(ttl="1h")
def station_series(station_name: str, start: str, end: str) -> pd.DataFrame:
    return _q(
        """
        select f.date_key, f.departures, f.arrivals, f.net_inflow
        from flows f join stations s on f.station_key = s.station_key
        where s.station_name = ? and f.date_key between ? and ?
        order by f.date_key
        """,
        [station_name, _key(start), _key(end)],
    )


def _key(d) -> int:
    """date / 'YYYY-MM-DD' -> YYYYMMDD int (the gold date_key)."""
    return int(pd.Timestamp(d).strftime("%Y%m%d"))
