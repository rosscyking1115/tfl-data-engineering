"""Statistical rigour battery for the disruption→demand association (ADR-0009).

Produces the numbers that turn the headline from a bare point estimate into a defensible,
uncertainty-quantified finding:

1.  **Bootstrap CI on the headline.** The headline statistic is the median deviation_ratio over
    disruption station-days (expected ≥ 5). Uncertainty comes from a CLUSTER bootstrap over
    event days (resample the 13 event days with replacement, pool their station-days, recompute
    the median) — days, not station-days, are the independent unit; station-days within a strike
    day are heavily correlated.
2.  **Per-event CIs.** Each event day's system ratio (Σactual/Σexpected) with a bootstrap over
    stations within the day.
3.  **Placebo (negative control).** The same headline statistic computed on 1,000 draws of
    13 random NON-disruption dates matched on day-of-week composition. If the pipeline
    manufactures signal, placebos will show it; the observed statistic should sit in the
    extreme tail of this null distribution.
4.  **Sensitivity battery.** The headline recomputed under: the weather-bucket thresholds the
    baseline conditions on (wet ≥ 0.5/1/2 mm × cold < 6/8/10 °C), the min-expected filter
    (3/5/10), and the baseline family (stratified median vs the LightGBM counterfactual).
    A result robust across reasonable choices is worth more than one hand-picked number.

Everything is deterministic (fixed seed) and reads only the committed gold Parquet.
Writes app/gold_export/analysis_rigor.json (small, committed — the app displays it).

Run:  .venv/Scripts/python analysis/rigor.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "app" / "gold_export"
SEED_CSV = ROOT / "dbt" / "seeds" / "disruption_dates.csv"
OUT = EXPORT / "analysis_rigor.json"

SEED = 42
N_BOOT = 2000          # bootstrap replicates (headline + per-event)
N_PLACEBO = 1000       # placebo draws
MIN_EXPECTED = 5.0     # primary spec's small-station filter


# ---------------------------------------------------------------- data loading

def load_deviation(source: str = "demand_deviation") -> pd.DataFrame:
    """Station-day deviation table (median or ML baseline), filtered to usable rows."""
    df = duckdb.sql(
        f"""
        select date_key, cast(date_day as date) as date_day, station_key,
               departures, expected_departures, deviation_ratio, is_disruption
        from read_parquet('{(EXPORT / f"{source}.parquet").as_posix()}')
        where expected_departures is not null and deviation_ratio is not null
        """
    ).df()
    df["date_day"] = pd.to_datetime(df["date_day"])
    return df


# ------------------------------------------------------------------ statistics

def headline_median(df: pd.DataFrame, min_expected: float = MIN_EXPECTED) -> float:
    """The headline statistic: median deviation_ratio over disruption station-days."""
    d = df[df["is_disruption"] & (df["expected_departures"] >= min_expected)]
    return float(d["deviation_ratio"].median())


def bootstrap_headline_ci(df: pd.DataFrame, rng: np.random.Generator,
                          n_boot: int = N_BOOT) -> tuple[float, float]:
    """Cluster bootstrap over event DAYS (the independent unit)."""
    d = df[df["is_disruption"] & (df["expected_departures"] >= MIN_EXPECTED)]
    by_day = {day: g["deviation_ratio"].to_numpy() for day, g in d.groupby("date_day")}
    days = list(by_day)
    stats = np.empty(n_boot)
    for b in range(n_boot):
        sample_days = rng.choice(len(days), size=len(days), replace=True)
        pooled = np.concatenate([by_day[days[i]] for i in sample_days])
        stats[b] = np.median(pooled)
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def per_event_cis(df: pd.DataFrame, rng: np.random.Generator) -> list[dict]:
    """System ratio per event day (Σactual/Σexpected) + a within-day station bootstrap."""
    events = pd.read_csv(SEED_CSV, parse_dates=["date"])
    d = df[df["is_disruption"] & (df["expected_departures"] >= MIN_EXPECTED)]
    out = []
    for day, g in d.groupby("date_day"):
        act = g["departures"].to_numpy(float)
        exp = g["expected_departures"].to_numpy(float)
        ratio = act.sum() / exp.sum()
        boots = np.empty(N_BOOT)
        n = len(g)
        for b in range(N_BOOT):
            idx = rng.integers(0, n, size=n)
            boots[b] = act[idx].sum() / exp[idx].sum()
        meta = events[events["date"] == day]
        out.append({
            "date": day.strftime("%Y-%m-%d"),
            "ratio": round(float(ratio), 3),
            "ci_lo": round(float(np.percentile(boots, 2.5)), 3),
            "ci_hi": round(float(np.percentile(boots, 97.5)), 3),
            "severity": meta["severity"].iloc[0] if not meta.empty else None,
            "n_stations": int(n),
        })
    return sorted(out, key=lambda e: e["date"])


def placebo_null(df: pd.DataFrame, rng: np.random.Generator,
                 n_draws: int = N_PLACEBO) -> dict:
    """Null distribution: the headline statistic on random non-disruption date sets,
    matched to the real events' day-of-week composition."""
    d = df[df["expected_departures"] >= MIN_EXPECTED]
    real_days = sorted(d.loc[d["is_disruption"], "date_day"].unique())
    real_dows = pd.Series(real_days).dt.dayofweek.value_counts().to_dict()

    normal = d[~d["is_disruption"]]
    normal_days = pd.Series(sorted(normal["date_day"].unique()))
    pool_by_dow = {dow: normal_days[normal_days.dt.dayofweek == dow].to_numpy()
                   for dow in real_dows}
    by_day = {day: g["deviation_ratio"].to_numpy() for day, g in normal.groupby("date_day")}

    observed = headline_median(df)
    null = np.empty(n_draws)
    for i in range(n_draws):
        picked = []
        for dow, k in real_dows.items():
            picked.extend(rng.choice(pool_by_dow[dow], size=k, replace=False))
        null[i] = np.median(np.concatenate([by_day[pd.Timestamp(p)] for p in picked]))
    p_value = float((null >= observed).mean())
    return {
        "n_draws": n_draws,
        "observed": round(observed, 3),
        "null_median": round(float(np.median(null)), 3),
        "null_p975": round(float(np.percentile(null, 97.5)), 3),
        "p_value_one_sided": p_value if p_value > 0 else f"< {1 / n_draws}",
        "dow_matched": True,
    }


# ------------------------------------------------------------ sensitivity battery

def headline_with_thresholds(wet_mm: float, cold_c: float,
                             min_expected: float = MIN_EXPECTED) -> float:
    """Recompute the whole median-baseline pipeline (expected_demand → deviation → headline)
    with different weather-bucket thresholds — the sensitivity the hand-picked cuts need."""
    q = f"""
    with flows as (
        select f.date_key, f.station_key, f.departures,
               cast(strptime(cast(f.date_key as varchar), '%Y%m%d') as date) as date_day
        from read_parquet('{(EXPORT / "station_daily_flows.parquet").as_posix()}') f
    ),
    wx as (
        select date_key,
               coalesce(precipitation_sum, 0) >= {wet_mm}          as is_wet,
               coalesce(temperature_2m_mean < {cold_c}, false)     as is_cold
        from read_parquet('{(EXPORT / "weather_daily.parquet").as_posix()}')
    ),
    enriched as (
        select fl.*, isodow(fl.date_day) as dow,
               coalesce(w.is_wet, false) as is_wet, coalesce(w.is_cold, false) as is_cold
        from flows fl left join wx w using (date_key)
    ),
    expected as (
        select station_key, dow, is_wet, is_cold, median(departures) as expected_departures
        from enriched group by 1, 2, 3, 4
    ),
    dev as (
        select e.date_day, e.departures / nullif(x.expected_departures, 0) as ratio,
               x.expected_departures
        from enriched e join expected x using (station_key, dow, is_wet, is_cold)
    ),
    strikes as (
        select cast(date as date) as date_day
        from read_csv_auto('{SEED_CSV.as_posix()}')
    )
    select median(ratio) from dev join strikes using (date_day)
    where expected_departures >= {min_expected} and ratio is not null
    """
    return round(float(duckdb.sql(q).fetchone()[0]), 3)


def sensitivity_battery() -> dict:
    thresholds = []
    for wet in (0.5, 1.0, 2.0):
        for cold in (6.0, 8.0, 10.0):
            thresholds.append({
                "wet_mm": wet, "cold_c": cold,
                "headline": headline_with_thresholds(wet, cold),
                "primary": wet == 1.0 and cold == 8.0,
            })
    med = load_deviation("demand_deviation")
    ml = load_deviation("demand_deviation_ml")
    min_exp = [{"min_expected": m, "headline": round(headline_median(med, m), 3)}
               for m in (3.0, 5.0, 10.0)]
    return {
        "weather_thresholds": thresholds,
        "min_expected_filter": min_exp,
        "baseline_family": {
            "stratified_median": round(headline_median(med), 3),
            "lightgbm_counterfactual": round(headline_median(ml), 3),
        },
    }


# ------------------------------------------------------------------------ main

def main() -> None:
    rng = np.random.default_rng(SEED)
    med = load_deviation("demand_deviation")

    headline = headline_median(med)
    ci_lo, ci_hi = bootstrap_headline_ci(med, rng)
    events = per_event_cis(med, rng)
    placebo = placebo_null(med, rng)
    sensitivity = sensitivity_battery()

    result = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "seed": SEED,
        "method": "cluster bootstrap over event days; dow-matched placebo; see ADR-0009",
        "headline": {
            "median_ratio": round(headline, 3),
            "ci95_lo": round(ci_lo, 3),
            "ci95_hi": round(ci_hi, 3),
            "n_events": int(med.loc[med["is_disruption"], "date_day"].nunique()),
            "n_bootstrap": N_BOOT,
        },
        "per_event": events,
        "placebo": placebo,
        "sensitivity": sensitivity,
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"headline: {headline:.3f}x  (95% CI {ci_lo:.3f}-{ci_hi:.3f})  "
          f"over {result['headline']['n_events']} events")
    print(f"placebo:  null median {placebo['null_median']}  null 97.5th {placebo['null_p975']}  "
          f"p(one-sided) {placebo['p_value_one_sided']}")
    print("sensitivity (weather cuts): " +
          ", ".join(f"{t['headline']:.2f}" for t in sensitivity["weather_thresholds"]))
    print(f"baselines: median {sensitivity['baseline_family']['stratified_median']} vs "
          f"ML {sensitivity['baseline_family']['lightgbm_counterfactual']}")
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
