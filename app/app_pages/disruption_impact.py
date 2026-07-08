"""Disruption impact — how tube/rail strikes shift cycling demand (the flagship)."""

import altair as alt
import streamlit as st

import data_access as da

st.title("Disruption impact on cycling demand")
st.caption(
    "When the Tube is disrupted, displaced journeys spill onto the cycle network. "
    "This measures the effect per day against a **weather-adjusted** baseline "
    "(station × day-of-week × wet/cold), so weather isn't mistaken for the strike."
)

head = da.disruption_headline()
if not head.empty:
    ratios = {r["day_type"]: r for _, r in head.iterrows()}
    with st.container(horizontal=True):
        for label in ("Normal days", "Disruption days"):
            if label in ratios:
                r = ratios[label]
                st.metric(label, f"{r['median_ratio']:.2f}× demand",
                          help=f"median across {int(r['n_dates'])} dates", border=True)
    st.caption("1.00× = exactly the weather-adjusted expectation. Disruption days run visibly higher.")

st.subheader("Every known disruption date, measured")
dates = da.disruption_dates()
chart = alt.Chart(dates).mark_bar().encode(
    x=alt.X("ratio:Q", title="Cycling demand vs weather-adjusted expected"),
    y=alt.Y("date_day:N", sort="-x", title=None),
    color=alt.condition(alt.datum.ratio >= 1, alt.value("#2563eb"), alt.value("#9ca3af")),
    tooltip=["date_day", "actual", "expected", "ratio", "severity"],
)
rule = alt.Chart(dates).mark_rule(color="#ef4444", strokeDash=[4, 4]).encode(x=alt.datum(1.0))
st.altair_chart(chart + rule, width="stretch")
st.caption(
    "Warm-weather strikes drive the biggest surges (up to ~2.3×). Cold-January strikes "
    "(2024-01-08/10) stay near or below baseline — the weather control makes that honest."
)

st.subheader("Where the demand landed")
picked = st.selectbox("Disruption date", dates["date_day"].astype(str).tolist())
movers = da.top_movers_on(picked)
if movers.empty:
    st.info("No station data for this date.")
else:
    bar = alt.Chart(movers).mark_bar().encode(
        x=alt.X("deviation:Q", title="Extra departures vs expected"),
        y=alt.Y("station_name:N", sort="-x", title=None),
        tooltip=["station_name", "departures", "expected", "deviation", "deviation_ratio"],
    )
    st.altair_chart(bar, width="stretch")
