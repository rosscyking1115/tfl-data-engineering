"""Usage trends — system-wide daily cycle-hire usage, 2022 → 2026."""

import altair as alt
import data_access as da
import pandas as pd
import streamlit as st

st.title("Usage trends")
st.caption(
    "41.4M journeys backfilled with Spark → Snowflake → dbt. This view reads the "
    "gold `daily_journey_stats` rollup (one row per day)."
)

lo, hi = da.date_bounds()
with st.sidebar:
    st.subheader("Filters")
    start, end = st.date_input("Date range", value=(lo, hi), min_value=lo, max_value=hi)
    grain = st.segmented_control("Granularity", ["Daily", "Monthly"], default="Daily")

df = da.daily_stats()
lo_ts, hi_ts = pd.Timestamp(start), pd.Timestamp(end)
df = df[(df["date_day"] >= lo_ts) & (df["date_day"] <= hi_ts)].copy()

if df.empty:
    st.info("No data in the selected range.")
    st.stop()

# KPI row
total = int(df["journeys"].sum())
avg_dur = (df["avg_duration_min"] * df["journeys"]).sum() / max(total, 1)
ebike = int(df["ebike_journeys"].sum())
ebike_share = ebike / total if total else 0
with st.container(horizontal=True):
    st.metric("Total journeys", f"{total:,}", border=True)
    st.metric("Avg duration (min)", f"{avg_dur:.1f}", border=True)
    st.metric("E-bike share", f"{ebike_share:.1%}", border=True)
    st.metric("Days covered", f"{len(df):,}", border=True)

st.caption(
    f"Across the selected range, **{ebike_share:.0%} of journeys are e-bike** and daily volume "
    "swings strongly with the seasons — the trend below shows both the seasonal cycle and the "
    "step change when the file format switched in Sept 2022."
)

if grain == "Monthly":
    df["period"] = df["date_day"].astype("datetime64[ns]").dt.to_period("M").dt.to_timestamp()
    plot = df.groupby("period", as_index=False).agg(journeys=("journeys", "sum"),
                                                    ebike_journeys=("ebike_journeys", "sum"))
    x = alt.X("period:T", title="Month")
else:
    plot = df.rename(columns={"date_day": "period"})
    x = alt.X("period:T", title="Date")

with st.container(border=True):
    st.subheader("Journeys over time")
    st.caption("The step up in Sep 2022 is the real schema-era switch (classic → next-gen files).")
    line = alt.Chart(plot).mark_line().encode(
        x=x, y=alt.Y("journeys:Q", title="Journeys"),
        tooltip=["period:T", "journeys:Q"],
    )
    st.altair_chart(line, width="stretch")

col1, col2 = st.columns(2)
with col1:
    with st.container(border=True):
        st.subheader("Weekday vs weekend")
        by_wk = df.assign(kind=df["is_weekend"].map({True: "Weekend", False: "Weekday"}))
        by_wk = by_wk.groupby("kind", as_index=False)["journeys"].mean()
        bar = alt.Chart(by_wk).mark_bar().encode(
            x=alt.X("kind:N", title=None), y=alt.Y("journeys:Q", title="Avg journeys/day"),
            color=alt.Color("kind:N", legend=None), tooltip=["kind", "journeys"],
        )
        st.altair_chart(bar, width="stretch")
with col2:
    with st.container(border=True):
        st.subheader("E-bike share over time")
        share = plot.assign(share=plot["ebike_journeys"] / plot["journeys"])
        area = alt.Chart(share).mark_area(opacity=0.7).encode(
            x=x, y=alt.Y("share:Q", title="E-bike share", axis=alt.Axis(format="%")),
            tooltip=["period:T", alt.Tooltip("share:Q", format=".1%")],
        )
        st.altair_chart(area, width="stretch")
