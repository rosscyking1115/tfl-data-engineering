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


# --- Disruption analytics (demand_deviation.parquet) ---

def _dev_path() -> str:
    return (EXPORT / "demand_deviation.parquet").as_posix()


@st.cache_data(ttl="1h")
def disruption_headline() -> pd.DataFrame:
    """Weather-adjusted median demand ratio: disruption days vs normal days."""
    return duckdb.connect().execute(
        f"""
        select case when is_disruption then 'Disruption days' else 'Normal days' end as day_type,
               count(distinct date_key) as n_dates,
               round(median(deviation_ratio), 3) as median_ratio
        from read_parquet('{_dev_path()}')
        where expected_departures >= 5
        group by 1 order by 1
        """
    ).df()


@st.cache_data(ttl="1h")
def disruption_dates() -> pd.DataFrame:
    """Per disruption date: system actual vs weather-adjusted expected + ratio."""
    return duckdb.connect().execute(
        f"""
        select date_day,
               sum(departures) as actual,
               round(sum(expected_departures)) as expected,
               round(sum(departures) / nullif(sum(expected_departures), 0), 2) as ratio,
               any_value(disruption_severity) as severity
        from read_parquet('{_dev_path()}')
        where is_disruption
        group by date_day order by date_day
        """
    ).df()


@st.cache_data(ttl="1h")
def top_movers_on(date_str: str, limit: int = 15) -> pd.DataFrame:
    """Stations with the largest positive demand deviation on a given date."""
    return duckdb.connect().execute(
        f"""
        select station_name, departures, round(expected_departures) as expected,
               deviation, deviation_ratio
        from read_parquet('{_dev_path()}')
        where date_day = ?::date and expected_departures >= 5
        order by deviation desc
        limit ?
        """,
        [date_str, limit],
    ).df()


# --- ML forecast layer (predicted_demand + demand_deviation_ml) ---

def _ml_dev_path() -> str:
    return (EXPORT / "demand_deviation_ml.parquet").as_posix()


@st.cache_data(ttl="1h")
def forecast_series(station_name: str) -> pd.DataFrame:
    """Actual vs the LightGBM baseline over time, for one station."""
    return duckdb.connect().execute(
        f"""
        select date_day,
               departures           as actual,
               expected_departures  as predicted,
               is_disruption
        from read_parquet('{_ml_dev_path()}')
        where station_name = ? and expected_departures is not null
        order by date_day
        """,
        [station_name],
    ).df()


@st.cache_data(ttl="1h")
def forecast_accuracy() -> pd.DataFrame:
    """Overall mean absolute error of the ML baseline vs the median baseline, on the
    same station-days (lower is better). The learned model is the sharper 'normal'."""
    return duckdb.connect().execute(
        f"""
        with ml as (
            select date_key, station_key, abs(deviation) e
            from read_parquet('{_ml_dev_path()}') where expected_departures is not null
        ),
        md as (
            select date_key, station_key, abs(deviation) e
            from read_parquet('{_dev_path()}') where expected_departures is not null
        )
        select round(avg(ml.e), 2) as ml_mae,
               round(avg(md.e), 2) as median_mae,
               count(*)            as n
        from ml join md on ml.date_key = md.date_key and ml.station_key = md.station_key
        """
    ).df()


@st.cache_data(ttl="1h")
def feature_importance() -> pd.DataFrame:
    path = EXPORT.parent.parent / "ml" / "model" / "feature_importance.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["gain_pct"] = 100 * df["gain"] / df["gain"].sum()
    return df


# --- Statistical rigour results (analysis/rigor.py -> committed JSON) ---

@st.cache_data(ttl="1h")
def rigor_results() -> dict:
    """Bootstrap CI, placebo and sensitivity battery for the headline (ADR-0009)."""
    import json

    path = EXPORT / "analysis_rigor.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# --- Live layer (live_*.parquet, refreshed by the daily GitHub Action) ---

@st.cache_data(ttl="15m")
def live_line_status() -> pd.DataFrame:
    path = EXPORT / "live_line_status.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    return df[df["snapshot_date"] == df["snapshot_date"].max()]


@st.cache_data(ttl="15m")
def live_bikepoint() -> pd.DataFrame:
    path = EXPORT / "live_bikepoint.parquet"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_parquet(path)
    return df[df["snapshot_date"] == df["snapshot_date"].max()]
