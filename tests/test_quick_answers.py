"""No-API Quick answers (app/quick_answers.py) — templated output over fixtures.

Loaders are monkeypatched so the templating logic is tested without Parquet or network.
"""

import data_access as da
import pandas as pd
import quick_answers as qa


def test_why_disrupted_lists_bad_lines(monkeypatch):
    df = pd.DataFrame([
        {"snapshot_date": "2026-07-09", "line_name": "District", "mode": "tube",
         "status_description": "Severe Delays", "reason": "Power supply failure.",
         "is_good_service": False},
        {"snapshot_date": "2026-07-09", "line_name": "Victoria", "mode": "tube",
         "status_description": "Good Service", "reason": None, "is_good_service": True},
    ])
    monkeypatch.setattr(da, "live_line_status", lambda: df)
    out = qa.why_disrupted()
    assert "District" in out and "Power supply failure." in out
    assert "Victoria" not in out  # good-service lines are not listed as disrupted


def test_why_disrupted_all_good(monkeypatch):
    df = pd.DataFrame([{"snapshot_date": "2026-07-09", "line_name": "Victoria", "mode": "tube",
                        "status_description": "Good Service", "reason": None, "is_good_service": True}])
    monkeypatch.setattr(da, "live_line_status", lambda: df)
    assert "Good service" in qa.why_disrupted()


def test_why_disrupted_empty(monkeypatch):
    monkeypatch.setattr(da, "live_line_status", lambda: pd.DataFrame())
    assert "No live" in qa.why_disrupted()


def test_busiest_stations_lists_rows(monkeypatch):
    df = pd.DataFrame({"station_name": ["Hyde Park", "Waterloo", "Kings Cross"],
                       "departures": [900, 800, 700], "arrivals": [1, 2, 3]})
    monkeypatch.setattr(da, "top_stations", lambda *a, **k: df)
    out = qa.busiest_stations(2024)
    assert "Hyde Park" in out and "900" in out and "2024" in out


def test_strike_effect(monkeypatch):
    df = pd.DataFrame({"day_type": ["Normal days", "Disruption days"],
                       "n_dates": [1000, 15], "median_ratio": [1.0, 1.33]})
    monkeypatch.setattr(da, "disruption_headline", lambda: df)
    assert "1.33" in qa.strike_effect()


def test_demand_trend(monkeypatch):
    df = pd.DataFrame({
        "date_day": pd.date_range("2026-03-01", periods=90),
        "journeys": [20000] * 90, "ebike_journeys": [4000] * 90, "avg_duration_min": [15.0] * 90,
    })
    monkeypatch.setattr(da, "daily_stats", lambda: df)
    out = qa.demand_trend()
    assert "journeys" in out.lower() and "%" in out


def test_station_lookup(monkeypatch):
    monkeypatch.setattr(da, "date_bounds", lambda: (pd.Timestamp("2022-01-01"), pd.Timestamp("2026-06-01")))
    monkeypatch.setattr(da, "station_series", lambda *a, **k: pd.DataFrame(
        {"departures": [100, 120], "arrivals": [90, 110], "net_inflow": [-10, -10]}))
    out = qa.station_lookup("Hyde Park Corner, Hyde Park")
    assert "Hyde Park Corner" in out and "220" in out  # 100+120 departures
