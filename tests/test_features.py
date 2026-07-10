"""Leakage guard + split-boundary tests for the ML feature build (ml/features.py).

The single most important correctness property of a temporal model is that no feature can see
the future. These tests exercise `add_features` on a synthetic, monotonic per-station series so
the lag/rolling logic is verifiable by hand — no Parquet, no network.
"""

import features as ft
import pandas as pd


def _raw(dates, stations=("A", "B")):
    rows = []
    for s in stations:
        for i, d in enumerate(dates):
            rows.append({
                "date_key": int(d.strftime("%Y%m%d")),
                "station_key": s,
                "station_name": f"Station {s}",
                "departures": 10 + i,  # strictly increasing so lags are checkable by eye
                "temperature_2m_mean": 10.0, "temperature_2m_max": 14.0,
                "precipitation_sum": 0.0, "rain_sum": 0.0, "wind_speed_10m_max": 5.0,
                "weather_code": 1, "is_wet": False, "is_cold": False,
            })
    return pd.DataFrame(rows)


def test_lag_and_rolling_never_leak_today():
    dates = pd.date_range("2024-11-01", "2024-12-15")  # 45 contiguous days
    feat = ft.add_features(_raw(dates))
    a = feat[feat["station_key"] == "A"].reset_index(drop=True)

    # prev-day lag is exactly yesterday's value; undefined on the first row
    assert pd.isna(a["dep_lag_1"].iloc[0])
    assert a["dep_lag_1"].iloc[1] == a["departures"].iloc[0]
    # same-day-last-week lag lines up 7 rows back
    assert a["dep_lag_7"].iloc[7] == a["departures"].iloc[0]
    # rolling means are built from the *shifted* series, so they never include today:
    # on a strictly increasing series that means they are always below today's value
    tail = a.iloc[8:]  # enough history for the windows to be populated
    assert (tail["roll_7"] < tail["departures"]).all()
    assert (tail["roll_28"] < tail["departures"]).all()


def test_lags_are_isolated_per_station():
    dates = pd.date_range("2024-11-01", "2024-11-20")
    feat = ft.add_features(_raw(dates, stations=("A", "B")))
    # each station's series starts fresh — the actual first row of every station has no prior
    # day (use .nth(0), not .first(): the latter returns the first *non-null* value per group)
    first_rows = feat.sort_values(["station_key", "date_key"]).groupby("station_key", observed=True).nth(0)
    assert first_rows["dep_lag_1"].isna().all()


def test_time_split_boundaries():
    dates = pd.date_range("2024-12-20", "2026-02-01")  # spans both split boundaries
    feat = ft.add_features(_raw(dates, stations=("A",)))
    assert (feat.loc[feat["date_key"] < ft.TRAIN_END, "split"] == "train").all()
    mid = feat[(feat["date_key"] >= ft.TRAIN_END) & (feat["date_key"] < ft.VAL_END)]
    assert (mid["split"] == "val").all()
    assert (feat.loc[feat["date_key"] >= ft.VAL_END, "split"] == "test").all()


def test_calendar_flags():
    feat = ft.add_features(_raw(pd.date_range("2024-12-23", "2025-01-02"), stations=("A",)))
    by_day = feat.set_index("date_day")
    assert by_day.loc["2024-12-25", "is_holiday"] == 1   # Christmas
    assert by_day.loc["2025-01-01", "is_holiday"] == 1   # New Year's Day
    assert by_day.loc["2024-12-28", "is_weekend"] == 1   # a Saturday
    assert by_day.loc["2024-12-27", "is_weekend"] == 0   # a Friday
