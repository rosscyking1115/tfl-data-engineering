"""Feature build for the station-level daily demand model.

Joins the committed gold Parquet (station_daily_flows + weather_daily) with the
disruption-dates seed and derives calendar, weather, disruption and per-station lag
features. Everything reads from `app/gold_export/` via DuckDB — no warehouse, same
durable source as the rest of the workflow (ADR-0006).

The target is daily `departures` per station. `is_disruption` is deliberately a
*feature*, not a filter: the model learns the strike uplift, and the "normal expected
demand" baseline is obtained by predicting with the flag switched off (the clean
counterfactual — see ADR-0008). Splits are strictly time-based, never random.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import holidays
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
EXPORT = ROOT / "app" / "gold_export"
SEED = ROOT / "dbt" / "seeds" / "disruption_dates.csv"

TARGET = "departures"

# Split boundaries (date_key = YYYYMMDD int). Train through 2024, validate on 2025,
# test on 2026-YTD. Journey data currently runs to ~2026-06.
TRAIN_END = 20250101   # train:  date_key <  TRAIN_END
VAL_END = 20260101     # val:    TRAIN_END <= date_key < VAL_END ; test: >= VAL_END

# Columns fed to the model. station_key + weather_code are categorical; the rest numeric.
CATEGORICALS = ["station_key", "weather_code"]
FEATURES = [
    # identity / calendar
    "station_key",
    "dow",
    "month",
    "day_of_year",
    "is_weekend",
    "is_holiday",
    # weather
    "temperature_2m_mean",
    "temperature_2m_max",
    "precipitation_sum",
    "rain_sum",
    "wind_speed_10m_max",
    "weather_code",
    "is_wet",
    "is_cold",
    # disruption (the counterfactual lever)
    "is_disruption",
    # per-station demand history (leakage-safe: all shifted by >=1 day)
    "dep_lag_1",
    "dep_lag_7",
    "roll_7",
    "roll_28",
]


def _load_raw() -> pd.DataFrame:
    """Flows left-joined to weather, straight from the gold Parquet via DuckDB."""
    con = duckdb.connect()
    try:
        df = con.execute(
            f"""
            select
                f.date_key,
                f.station_key,
                f.station_name,
                f.departures,
                w.temperature_2m_mean,
                w.temperature_2m_max,
                w.precipitation_sum,
                w.rain_sum,
                w.wind_speed_10m_max,
                w.weather_code,
                coalesce(w.is_wet, false)  as is_wet,
                coalesce(w.is_cold, false) as is_cold
            from read_parquet('{(EXPORT / "station_daily_flows.parquet").as_posix()}') f
            left join read_parquet('{(EXPORT / "weather_daily.parquet").as_posix()}') w
                on f.date_key = w.date_key
            order by f.station_key, f.date_key
            """
        ).df()
    finally:
        con.close()
    return df


def _disruption_dates() -> set:
    dd = pd.read_csv(SEED)
    return set(pd.to_datetime(dd["date"]).dt.normalize())


def build_dataset() -> pd.DataFrame:
    """Full modelling frame: one row per station-day, features + target + split label."""
    df = _load_raw()
    df["date_day"] = pd.to_datetime(df["date_key"], format="%Y%m%d")

    # --- calendar ---
    df["dow"] = df["date_day"].dt.isocalendar().day.astype("int16")  # 1=Mon..7=Sun
    df["month"] = df["date_day"].dt.month.astype("int16")
    df["day_of_year"] = df["date_day"].dt.dayofyear.astype("int16")
    df["is_weekend"] = (df["dow"] >= 6).astype("int8")

    yrs = range(df["date_day"].dt.year.min(), df["date_day"].dt.year.max() + 1)
    uk = holidays.UnitedKingdom(subdiv="England", years=yrs)
    hol = {pd.Timestamp(d).normalize() for d in uk}
    df["is_holiday"] = df["date_day"].dt.normalize().isin(hol).astype("int8")

    # --- disruption flag (the counterfactual lever) ---
    df["is_disruption"] = df["date_day"].dt.normalize().isin(_disruption_dates()).astype("int8")

    # --- weather typing ---
    df["is_wet"] = df["is_wet"].astype("int8")
    df["is_cold"] = df["is_cold"].astype("int8")
    # category dtype (sorted, deterministic) so LightGBM's categorical codes are stable
    # across train / batch-predict / serve — provided every caller rebuilds from the same
    # full Parquet (build_dataset), which fixes the category set and therefore the codes.
    df["weather_code"] = df["weather_code"].astype("category")

    # --- per-station lags (frame is already sorted by station_key, date_key) ---
    # Contiguous daily rows per station; NaNs at each series start are left for LightGBM
    # to handle natively (no imputation). All lags are shifted so today never leaks.
    g = df.groupby("station_key", observed=True)[TARGET]
    df["dep_lag_1"] = g.shift(1)
    df["dep_lag_7"] = g.shift(7)
    lag1 = df.groupby("station_key", observed=True)["dep_lag_1"]
    df["roll_7"] = lag1.transform(lambda s: s.rolling(7, min_periods=1).mean())
    df["roll_28"] = lag1.transform(lambda s: s.rolling(28, min_periods=1).mean())

    df["station_key"] = df["station_key"].astype("category")

    # --- time-based split label ---
    df["split"] = "train"
    df.loc[df["date_key"] >= TRAIN_END, "split"] = "val"
    df.loc[df["date_key"] >= VAL_END, "split"] = "test"
    return df


def split_frames(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {s: df[df["split"] == s].copy() for s in ("train", "val", "test")}


def xy(frame: pd.DataFrame):
    return frame[FEATURES], frame[TARGET]


if __name__ == "__main__":
    d = build_dataset()
    print(f"rows={len(d):,}  stations={d['station_key'].nunique()}  "
          f"dates {d['date_day'].min().date()}→{d['date_day'].max().date()}")
    print(d["split"].value_counts().reindex(["train", "val", "test"]).to_string())
    print(f"disruption rows: {int(d['is_disruption'].sum()):,}")
    print("\nnull rates on lag features (expected small — series starts only):")
    print(d[["dep_lag_1", "dep_lag_7", "roll_7", "roll_28"]].isna().mean().round(4).to_string())
