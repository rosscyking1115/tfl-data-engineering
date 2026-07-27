"""Snapshot coverage, freshness and daily-run metadata."""

from datetime import date, datetime, timezone

import altair as alt
import data_access as da
import pandas as pd
import streamlit as st
from snapshot_coverage import calculate_snapshot_coverage

COLLECTION_START = date(2026, 7, 8)  # forward disruption log began here (ADR-0009 two-horizon)

# Only these two gaps have a diagnosed cause. Any other missing day must report as
# unexplained rather than inheriting this incident's write-up.
DIAGNOSED_GAPS = {
    date(2026, 7, 11): "a fill-rate NA crash",
    date(2026, 7, 12): "a branch-protection push block",
}

st.title("Pipeline health")
st.caption(
    "The daily job snapshots the live network, ingests new journey CSVs and rebuilds the "
    "analytics layer behind dbt tests. The API has no history, so a missed snapshot is a "
    "**permanent** gap. This page reports coverage, freshness and run metadata."
)

# full (unfiltered) snapshot history for coverage — not just the latest day
ls_all = da.line_status_history()
if ls_all.empty:
    st.info("No snapshot history has been committed yet. The daily job will populate this page.")
    st.stop()
collected = sorted(pd.to_datetime(ls_all["snapshot_date"]).dt.date.unique())
snapshot_status = calculate_snapshot_coverage(
    collected,
    start_date=COLLECTION_START,
    now_utc=datetime.now(timezone.utc),
)
expected = snapshot_status.expected
missing = snapshot_status.missing
coverage = snapshot_status.coverage

# journey side
daily = da.daily_stats()
j_max = pd.to_datetime(daily["date_day"]).max().date()

rlog = da.run_log()

with st.container(horizontal=True):
    st.metric("Snapshot coverage", f"{coverage:.0%}", border=True,
              help=(f"{snapshot_status.covered_days}/{len(expected)} due days since "
                    f"collection began {COLLECTION_START}"))
    st.metric("Latest snapshot", str(max(collected)) if collected else "—", border=True)
    st.metric("Journey data through", str(j_max), border=True,
              help="TfL publishes journey extracts with a ~1–2 month lag (ADR-0006)")
    if not rlog.empty:
        st.metric("Last gated run", str(rlog["run_ts"].iloc[-1])[:10], border=True,
                  help=f"dbt build: {rlog['dbt_build'].iloc[-1]}")

if snapshot_status.pending is not None:
    st.info(
        f"**Today's snapshot ({snapshot_status.pending}) is pending.** The daily job is "
        "scheduled for 06:17 UTC; today enters the coverage calculation after 06:30 UTC.",
        icon=":material/schedule:",
    )

if missing:
    diagnosed = [m for m in missing if m in DIAGNOSED_GAPS]
    undiagnosed = [m for m in missing if m not in DIAGNOSED_GAPS]
    parts = [
        f"**{len(missing)} permanently missed snapshot day(s).** The API keeps no history, so "
        "these holes are permanent and remain visible here."
    ]
    if diagnosed:
        causes = "; ".join(f"{m} — {DIAGNOSED_GAPS[m]}" for m in diagnosed)
        parts.append(f"**Diagnosed ({len(diagnosed)}):** {causes}. Both since fixed.")
    if undiagnosed:
        parts.append(
            f"**Not yet diagnosed ({len(undiagnosed)}):** "
            + ", ".join(str(m) for m in undiagnosed)
            + ". No cause has been recorded for these — check the run log below and the "
            "workflow history before treating them as explained."
        )
    st.warning("\n\n".join(parts), icon=":material/report:")
else:
    st.success("No gaps in the disruption snapshot log.", icon=":material/verified:")

with st.container(border=True):
    st.subheader("Snapshot volume by day", anchor=False)
    st.caption("Rows collected per daily snapshot. A sudden drop indicates an upstream problem "
               "even if the run went green.")
    vol = ls_all.groupby("snapshot_date").size().reset_index(name="line_status_rows")
    chart = alt.Chart(vol).mark_bar(color="#2563eb").encode(
        x=alt.X("snapshot_date:N", title=None),
        y=alt.Y("line_status_rows:Q", title="line-status rows"),
        tooltip=["snapshot_date", "line_status_rows"],
    ).properties(height=220)
    st.altair_chart(chart, width="stretch")

if not rlog.empty:
    with st.container(border=True):
        st.subheader("Run metadata (the audit trail)", anchor=False)
        st.dataframe(rlog.tail(30).iloc[::-1], hide_index=True, width="stretch")
else:
    st.caption("Run-metadata table appears after the first gated daily run commits `run_log.parquet`.")

st.caption(
    "The workflow uses idempotent upserts, API retry and backoff, row-count and schema gates, "
    "dbt tests, a <26-hour freshness tripwire and an automatically opened GitHub issue after a failed run."
)
