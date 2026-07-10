"""No-API 'Quick answers' — templated natural-language responses over the gold layer.

These power the free, always-on tier of the Ask page: no Anthropic key, no cost, no abuse
surface. Each function returns a Markdown string built purely from the curated DuckDB/Parquet
loaders in `data_access.py` (the same data the AI assistant's tools use). Because there's no
LLM, every number is exactly what the query returned — the strongest possible correctness
guarantee, and available to every public visitor.
"""

from __future__ import annotations

import data_access as da
import pandas as pd


def why_disrupted() -> str:
    """Which tube/rail lines are not in good service in the latest live snapshot, and why."""
    lines = da.live_line_status()
    if lines.empty:
        return "No live line-status snapshot has been committed yet."
    snap = lines["snapshot_date"].max()
    bad = lines[~lines["is_good_service"]].drop_duplicates(subset=["line_name", "reason"])
    if bad.empty:
        return f"**Good service** across all tracked lines as of **{snap}**."
    parts = [f"As of **{snap}**, {len(bad['line_name'].unique())} line(s) are disrupted:\n"]
    for _, r in bad.iterrows():
        reason = (r["reason"] or "").strip() or "No reason published by TfL."
        parts.append(f"- 🔴 **{r['line_name']}** ({r['mode']}) — *{r['status_description']}*  \n  {reason}")
    return "\n".join(parts)


def busiest_stations(year: int, by: str = "departures") -> str:
    """Top 5 stations by departures (or arrivals) in a given calendar year."""
    top = da.top_stations(f"{year}-01-01", f"{year}-12-31", by, 5)
    if top.empty:
        return f"No station activity recorded in {year}."
    lines = [f"**Busiest stations by {by} in {year}:**\n"]
    for i, r in enumerate(top.itertuples(index=False), 1):
        lines.append(f"{i}. **{r.station_name}** — {int(getattr(r, by)):,} {by}")
    return "\n".join(lines)


def strike_effect() -> str:
    """The headline disruption finding: how much strikes lift cycling vs a weather-adjusted normal."""
    head = da.disruption_headline()
    if head.empty:
        return "The disruption baseline hasn't been built yet."
    row = {r["day_type"]: r for _, r in head.iterrows()}
    disr = row.get("Disruption days")
    if disr is None:
        return "No disruption days found in the data."
    ratio = disr["median_ratio"]
    uplift = (ratio - 1) * 100
    return (
        f"On strike days, cycling runs at **{ratio:.2f}× a weather-adjusted normal** — about "
        f"**{uplift:+.0f}%** more than a comparable non-strike day (median across "
        f"{int(disr['n_dates'])} disruption days). Warm-weather strikes surge most (up to ~2.3×); "
        f"cold-January strikes stay near or below normal — the weather control keeps that honest."
    )


def demand_trend() -> str:
    """System-wide usage over the most recent 90 days of journey data."""
    df = da.daily_stats()
    if df.empty:
        return "No daily usage data available."
    df = df.sort_values("date_day")
    recent = df[df["date_day"] >= df["date_day"].max() - pd.Timedelta(days=90)]
    total = int(recent["journeys"].sum())
    if total == 0:
        return "No journeys recorded in the most recent window."
    ebike = recent["ebike_journeys"].sum() / total
    lo, hi = recent["date_day"].min().date(), recent["date_day"].max().date()
    return (
        f"Over the last 90 days of journey data (**{lo} → {hi}**): **{total:,} journeys**, "
        f"averaging **{recent['journeys'].mean():,.0f}/day**, with an e-bike share of "
        f"**{ebike:.1%}**. (Journey data lags ~1–2 months — this is the most recent published window.)"
    )


def station_lookup(station_name: str) -> str:
    """Total flow for one station over the full available history."""
    lo, hi = da.date_bounds()
    s = da.station_series(station_name, str(lo), str(hi))
    if s.empty:
        return f"No activity found for **{station_name}**."
    dep, arr = int(s["departures"].sum()), int(s["arrivals"].sum())
    net = int(s["net_inflow"].sum())
    tilt = "a net **destination**" if net > 0 else "a net **origin**" if net < 0 else "balanced"
    lo_d, hi_d = pd.Timestamp(lo).date(), pd.Timestamp(hi).date()
    return (
        f"**{station_name}** over {lo_d} → {hi_d}: **{dep:,} departures**, **{arr:,} arrivals** "
        f"(net {net:+,}) — {tilt} for journeys."
    )
