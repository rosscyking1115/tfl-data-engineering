"""Busiest stations and station-level flow over time."""

import altair as alt
import data_access as da
import pandas as pd
import streamlit as st
import ui

st.title("Station explorer")
st.caption("Reads the gold `station_daily_flows` rollup (station × day) joined to `dim_station`.")

lo, hi = da.date_bounds()
with st.sidebar:
    st.subheader("Filters")
    start, end = ui.date_range_input("Date range", lo, hi, key="explorer_range")
    # required=True: deselecting would return None and render "Busiest N stations by None".
    by = st.segmented_control("Rank by", ["departures", "arrivals"],
                              default="departures", required=True)
    top_n = st.slider("How many stations", 5, 25, 10)

with st.container(border=True):
    st.subheader(f"Busiest {top_n} stations by {by}")
    top = da.top_stations(str(start), str(end), by, top_n)
    chart = alt.Chart(top).mark_bar(color="#2563eb").encode(
        x=alt.X(f"{by}:Q", title=f"Total {by} in range"),
        y=alt.Y("station_name:N", sort="-x", title=None, axis=alt.Axis(labelLimit=240)),
        tooltip=[
            alt.Tooltip("station_name:N", title="Station"),
            alt.Tooltip("departures:Q", title="Departures", format=","),
            alt.Tooltip("arrivals:Q", title="Arrivals", format=","),
        ],
    ).properties(height=max(300, top_n * 26))
    st.altair_chart(chart, width="stretch")
    st.caption("The highest departure counts are concentrated around parks, mainline stations, "
               "the West End, the City and the riverside.")

with st.container(border=True):
    st.subheader("Single-station flow over time")
    stations = da.station_names()
    default = stations.index("Hyde Park Corner, Hyde Park") \
        if "Hyde Park Corner, Hyde Park" in stations else 0
    station = st.selectbox("Station", stations, index=default)
    series = da.station_series(station, str(start), str(end))
    if series.empty:
        st.info("No activity for this station in range.")
    else:
        series["date"] = pd.to_datetime(series["date_key"].astype(str), format="%Y%m%d")
        long = series.melt(id_vars="date", value_vars=["departures", "arrivals"],
                           var_name="direction", value_name="count")
        chart = alt.Chart(long).mark_line().encode(
            x=alt.X("date:T", title=None), y=alt.Y("count:Q", title="Journeys"),
            color=alt.Color("direction:N", title=None),
            tooltip=["date:T", "direction:N", "count:Q"],
        )
        st.altair_chart(chart, width="stretch")
        st.caption(f"Net inflow over range: {int(series['net_inflow'].sum()):+,} "
                   "(arrivals − departures)")
