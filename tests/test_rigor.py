"""Statistical-rigour battery (analysis/rigor.py) — logic checks on synthetic data.

The bootstrap/placebo machinery must (a) recover a known effect, (b) produce intervals that
cover it, and (c) NOT find an effect in null data. All on tiny synthetic frames, no Parquet.
"""

import numpy as np
import pandas as pd
import rigor


def _frame(effect: float, n_days: int = 8, n_stations: int = 40, seed: int = 0) -> pd.DataFrame:
    """Synthetic deviation table: normal days ratio~1, disruption days ratio~effect."""
    rng = np.random.default_rng(seed)
    rows = []
    for d in range(60):
        day = pd.Timestamp("2024-01-01") + pd.Timedelta(days=d)
        is_dis = d < n_days
        centre = effect if is_dis else 1.0
        for s in range(n_stations):
            rows.append({
                "date_key": int(day.strftime("%Y%m%d")), "date_day": day,
                "station_key": f"s{s}", "departures": 20,
                "expected_departures": 20.0,
                "deviation_ratio": float(rng.normal(centre, 0.1)),
                "is_disruption": is_dis,
            })
    return pd.DataFrame(rows)


def test_headline_recovers_known_effect():
    df = _frame(effect=1.4)
    assert abs(rigor.headline_median(df) - 1.4) < 0.05


def test_bootstrap_ci_covers_effect_and_is_ordered():
    df = _frame(effect=1.4)
    lo, hi = rigor.bootstrap_headline_ci(df, np.random.default_rng(1), n_boot=200)
    assert lo < hi
    assert lo < 1.4 < hi


def test_placebo_finds_no_effect_in_null_data():
    df = _frame(effect=1.0)  # "disruption" days are indistinguishable from normal
    out = rigor.placebo_null(df, np.random.default_rng(2), n_draws=100)
    # observed sits inside the null distribution -> large p, no manufactured signal
    assert isinstance(out["p_value_one_sided"], float)
    assert out["p_value_one_sided"] > 0.05


def test_placebo_detects_real_effect():
    df = _frame(effect=1.4)
    out = rigor.placebo_null(df, np.random.default_rng(3), n_draws=100)
    p = out["p_value_one_sided"]
    assert (isinstance(p, str) and p.startswith("<")) or p < 0.05


def test_haversine_known_distance():
    # Hyde Park Corner (51.5027, -0.1527) -> Bank (51.5133, -0.0886): ~4.6 km
    d = float(rigor.haversine_km(51.5027, -0.1527, 51.5133, -0.0886))
    assert 4.0 < d < 5.2


def test_stations_near_line_radius_rule():
    geo = pd.DataFrame({
        "station_key": ["near", "far"],
        "lat": [51.5030, 51.6000],   # 'near' ~0.05km from the stop; 'far' ~11km away
        "lon": [-0.1527, -0.1527],
    })
    stops = pd.DataFrame({"line_id": ["central"], "lat": [51.5027], "lon": [-0.1520]})
    assert rigor.stations_near_line("central", 0.5, geo, stops) == {"near"}
    assert rigor.stations_near_line("central", 15.0, geo, stops) == {"near", "far"}
    assert rigor.stations_near_line("victoria", 0.5, geo, stops) == set()  # no stops -> empty
