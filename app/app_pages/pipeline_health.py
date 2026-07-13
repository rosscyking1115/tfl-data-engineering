"""Pipeline health — the workflow watching itself (rigor-pass Area 5, ADR-0009 §honesty)."""

from datetime import date

import altair as alt
import data_access as da
import pandas as pd
import streamlit as st

COLLECTION_START = date(2026, 7, 8)  # forward disruption log began here (ADR-0009 two-horizon)

st.title("Pipeline health")
st.caption(
    "The daily job snapshots the live network (a missed day is a **permanent** hole — the API "
    "has no history), ingests newly published journey CSVs, and rebuilds the analytics layer "
    "gated by dbt tests. This page is the pipeline watching itself: coverage, freshness and "
    "run metadata, gaps included."
)

# full (unfiltered) snapshot history for coverage — not just the latest day
ls_all = pd.read_parquet(da.EXPORT / "live_line_status.parquet")
collected = sorted(pd.to_datetime(ls_all["snapshot_date"]).dt.date.unique())
expected = pd.date_range(COLLECTION_START, date.today()).date
missing = sorted(set(expected) - set(collected))
coverage = 1 - len(missing) / max(len(expected), 1)

# journey side
daily = da.daily_stats()
j_max = pd.to_datetime(daily["date_day"]).max().date()

rlog = None
p = da.EXPORT / "run_log.parquet"
if p.exists():
    rlog = pd.read_parquet(p).sort_values("run_ts")

with st.container(horizontal=True):
    st.metric("Snapshot coverage", f"{coverage:.0%}", border=True,
              help=f"{len(collected)}/{len(expected)} days since collection began {COLLECTION_START}")
    st.metric("Latest snapshot", str(max(collected)) if collected else "—", border=True)
    st.metric("Journey data through", str(j_max), border=True,
              help="TfL publishes journey extracts with a ~1–2 month lag (ADR-0006)")
    if rlog is not None and not rlog.empty:
        st.metric("Last gated run", str(rlog["run_ts"].iloc[-1])[:10], border=True,
                  help=f"dbt build: {rlog['dbt_build'].iloc[-1]}")

if missing:
    st.warning(
        f"**{len(missing)} permanently missed snapshot day(s):** "
        + ", ".join(str(m) for m in missing)
        + " — the scheduled job failed on these dates (2026-07-11/12: a fill-rate NA crash plus "
        "a branch-protection push block; both fixed). The API keeps no history, so these holes "
        "are honest and permanent — exactly why the freshness tripwire and this page exist.",
        icon=":material/report:",
    )
else:
    st.success("No gaps in the disruption snapshot log.", icon=":material/verified:")

with st.container(border=True):
    st.subheader("Snapshot volume by day", anchor=False)
    st.caption("Rows collected per daily snapshot — a sudden drop means an upstream problem "
               "even if the run went green.")
    vol = ls_all.groupby("snapshot_date").size().reset_index(name="line_status_rows")
    chart = alt.Chart(vol).mark_bar(color="#2563eb").encode(
        x=alt.X("snapshot_date:N", title=None),
        y=alt.Y("line_status_rows:Q", title="line-status rows"),
        tooltip=["snapshot_date", "line_status_rows"],
    ).properties(height=220)
    st.altair_chart(chart, width="stretch")

if rlog is not None and not rlog.empty:
    with st.container(border=True):
        st.subheader("Run metadata (the audit trail)", anchor=False)
        st.dataframe(rlog.tail(30).iloc[::-1], hide_index=True, width="stretch")
else:
    st.caption("Run-metadata table appears after the first gated daily run commits `run_log.parquet`.")

st.caption(
    "Reliability design: idempotent upserts (safe re-runs), retry/backoff on API calls, "
    "row-count + schema gates that fail loudly, dbt tests gating delivery, a freshness "
    "tripwire (<26h), and an auto-opened GitHub issue on any red run."
)
