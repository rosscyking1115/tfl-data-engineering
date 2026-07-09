"""Today's network — the live layer, refreshed daily by the GitHub Action."""

import altair as alt
import streamlit as st

import data_access as da

st.title("Today's network")
st.caption("Live TfL Line Status + BikePoint dock occupancy, refreshed daily by a "
           "GitHub Actions job writing Parquet to the repo.")

lines = da.live_line_status()
docks = da.live_bikepoint()

if lines.empty and docks.empty:
    st.info("No live snapshot committed yet — the daily job populates this.")
    st.stop()

if not lines.empty:
    snap = lines["snapshot_date"].max()
    st.caption(f"Latest snapshot: {snap}")
    disrupted = lines[~lines["is_good_service"]]
    n_bad = int((~lines["is_good_service"]).sum())
    st.markdown(
        f"**{n_bad} line(s) are not in good service right now.**"
        if n_bad else "**All tracked lines are running a good service right now.**"
    )
    with st.container(horizontal=True):
        st.metric("Lines tracked", lines["line_id"].nunique(), border=True)
        st.metric("Not good service", n_bad, border=True)
    with st.container(border=True):
        st.subheader("Line status")
        if disrupted.empty:
            st.success("Good service across all tracked lines.")
        else:
            st.dataframe(
                disrupted[["line_name", "mode", "status_description", "reason"]],
                hide_index=True, width="stretch",
            )

if not docks.empty:
    with st.container(border=True):
        st.subheader("Dock occupancy right now")
        empty = int((docks["n_bikes"] == 0).sum())
        full = int((docks["n_empty_docks"] == 0).sum())
        with st.container(horizontal=True):
            st.metric("Docking stations", len(docks), border=True)
            st.metric("Empty (no bikes)", empty, border=True)
            st.metric("Full (no spaces)", full, border=True)
        hist = alt.Chart(docks.dropna(subset=["fill_rate"])).mark_bar().encode(
            x=alt.X("fill_rate:Q", bin=alt.Bin(maxbins=20), title="Fill rate (bikes / docks)"),
            y=alt.Y("count():Q", title="Stations"),
        )
        st.altair_chart(hist, width="stretch")
