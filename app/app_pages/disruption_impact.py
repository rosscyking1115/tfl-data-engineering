"""Disruption impact — how tube/rail strikes shift cycling demand (the flagship)."""

import altair as alt
import pandas as pd
import streamlit as st

import data_access as da

BLUE, GREY, RED = "#2563eb", "#9ca3af", "#ef4444"

st.title("Disruption impact on cycling demand")
st.caption(
    "When the Tube is disrupted, displaced journeys spill onto the cycle network. "
    "Every strike day is compared against a **weather-adjusted normal** — the same station, "
    "same weekday, same wet/cold conditions — so ordinary weather is never mistaken for the "
    "strike effect."
)

# --- Headline: the whole story in two numbers -------------------------------------------
head = da.disruption_headline()
if not head.empty:
    ratios = {r["day_type"]: r for _, r in head.iterrows()}
    normal = ratios.get("Normal days")
    disr = ratios.get("Disruption days")
    with st.container(horizontal=True):
        if normal is not None:
            st.metric(
                "A normal day", f"{normal['median_ratio']:.2f}× demand", border=True,
                help=f"Baseline — median across {int(normal['n_dates'])} normal days",
            )
        if disr is not None:
            uplift = (disr["median_ratio"] - 1) * 100
            st.metric(
                "A strike day", f"{disr['median_ratio']:.2f}× demand",
                delta=f"{uplift:+.0f}% vs normal", border=True,
                help=f"Median across {int(disr['n_dates'])} disruption days",
            )
    st.caption(
        "Read as a multiple of normal: **1.00× = exactly expected**, so 1.33× means a third "
        "more cycling than a comparable non-strike day."
    )

# --- Every strike day, ranked --------------------------------------------------------------
st.subheader("Every strike day, ranked by how much cycling jumped")
dates = da.disruption_dates()
dates["day"] = pd.to_datetime(dates["date_day"]).dt.strftime("%d %b %Y")

bars = alt.Chart(dates).mark_bar().encode(
    x=alt.X("ratio:Q", title="Cycling demand vs a normal day  (1.0 = normal)"),
    y=alt.Y("day:N", sort="-x", title=None, axis=alt.Axis(labelLimit=140)),
    color=alt.condition(alt.datum.ratio >= 1, alt.value(BLUE), alt.value(GREY)),
    tooltip=[
        alt.Tooltip("day:N", title="Date"),
        alt.Tooltip("actual:Q", title="Actual departures", format=","),
        alt.Tooltip("expected:Q", title="Normal (expected)", format=","),
        alt.Tooltip("ratio:Q", title="Ratio (×)"),
        alt.Tooltip("severity:N", title="Severity"),
    ],
).properties(height=430)
rule = alt.Chart(dates).mark_rule(color=RED, strokeDash=[4, 4]).encode(x=alt.datum(1.0))
st.altair_chart(bars + rule, width="stretch")
st.caption(
    "Blue = more cycling than normal; the dashed red line is a normal day. Warm-weather "
    "strikes drive the biggest surges (up to ~2.3×), while the cold-January 2024 strikes sit "
    "*below* the line — people didn't switch to bikes in the cold. The weather adjustment is "
    "what makes that distinction honest."
)

# --- Where the demand landed ---------------------------------------------------------------
st.subheader("Where the extra bikes were hired, station by station")
options = dates.sort_values("date_day", ascending=False)
picked = st.selectbox(
    "Pick a strike day",
    options["date_day"].astype(str).tolist(),
    format_func=lambda d: pd.to_datetime(d).strftime("%d %b %Y"),
)
movers = da.top_movers_on(picked)
if movers.empty:
    st.caption("No station-level data for this date.")
else:
    chart = alt.Chart(movers).mark_bar(color=BLUE).encode(
        x=alt.X("deviation:Q", title="Extra departures vs a normal day"),
        y=alt.Y("station_name:N", sort="-x", title=None, axis=alt.Axis(labelLimit=230)),
        tooltip=[
            alt.Tooltip("station_name:N", title="Station"),
            alt.Tooltip("departures:Q", title="Actual", format=","),
            alt.Tooltip("expected:Q", title="Normal", format=","),
            alt.Tooltip("deviation:Q", title="Extra trips", format=","),
            alt.Tooltip("deviation_ratio:Q", title="Ratio (×)"),
        ],
    ).properties(height=460)
    st.altair_chart(chart, width="stretch")
    st.caption(
        "Each bar is one docking station's extra hires that day versus its own weather-adjusted "
        "normal. The surge concentrates around Tube interchanges and business districts — exactly "
        "where displaced commuters need an alternative."
    )
