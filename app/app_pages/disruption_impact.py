"""How Tube and rail strikes change cycle-hire demand."""

import altair as alt
import data_access as da
import pandas as pd
import streamlit as st

BLUE, GREY, RED = "#2563eb", "#9ca3af", "#ef4444"

st.title("Disruption impact on cycling demand")
st.caption(
    "Each strike day is compared with a **weather-adjusted normal** for the same station, "
    "weekday and wet or cold conditions. This separates the observed disruption association "
    "from ordinary weather variation."
)

# --- Certified headline ---------------------------------------------------------------
rigor = da.certified_evidence()
lineage = da.certified_evidence_lineage()
certificate = rigor["certificate"]
hl = rigor["headline"]
if hl:
    with st.container(horizontal=True):
        st.metric(
            "Certified strike-day association", f"{hl['median_ratio']:.2f}× demand", border=True,
            help=(f"95% CI {hl['ci95_lo']:.2f}–{hl['ci95_hi']:.2f}×; "
                  f"bootstrap over {hl['n_events']} event days (ADR-0009)"),
        )
    st.caption(certificate["permitted_claim"])
    st.caption(
        f"Certificate `{certificate['certificate_id']}` · {certificate['evidence_version']} · "
        f"comparator: {certificate['primary_specification']['comparator_family']} · "
        f"eligible station-days: expected departures ≥ "
        f"{certificate['primary_specification']['min_expected_departures']}."
    )
    with st.expander("Evidence lineage", icon=":material/account_tree:"):
        st.markdown(
            "The certified result is read from the versioned rigor export; this page does not "
            "recalculate it from station-day data."
        )
        st.markdown(
            f"- **Source-cited strike seed:** `{lineage['source_cited_strike_seed']}`\n"
            f"- **Station × day evidence:** `{lineage['station_day_evidence']}`\n"
            f"- **Certified artifact:** `{lineage['evidence_artifact']}`\n"
            f"- **Forward disruption log:** `{lineage['forward_event_log']}` — collected forward "
            "only, so it is diagnostic rather than deep historical coverage."
        )

if rigor:
    with st.expander("Placebo and sensitivity checks", icon=":material/science:"):
        pl = rigor.get("placebo", {})
        if pl:
            st.markdown(
                f"**Placebo (negative control):** the same statistic on {pl['n_draws']:,} random "
                f"sets of non-strike dates (day-of-week matched) has a null median of "
                f"**{pl['null_median']}×** and a 97.5th percentile of **{pl['null_p975']}×**. "
                f"The observed **{pl['observed']}×** is outside that distribution "
                f"(one-sided p {pl['p_value_one_sided']})."
            )
        sens = rigor.get("sensitivity", {})
        if sens.get("weather_thresholds"):
            tbl = pd.DataFrame(sens["weather_thresholds"])
            tbl = tbl.rename(columns={"wet_mm": "wet ≥ (mm)", "cold_c": "cold < (°C)",
                                      "headline": "headline ×", "primary": "primary spec"})
            st.markdown("**Sensitivity to the weather-bucket thresholds.** These thresholds are "
                        "the baseline's main discretionary choice:")
            st.dataframe(tbl, hide_index=True, width="content")
        fam = sens.get("baseline_family", {})
        if fam:
            st.markdown(
                f"**Baseline family:** stratified median **{fam['stratified_median']}×**; "
                f"LightGBM counterfactual **{fam['lightgbm_counterfactual']}×**. The independently "
                f"built baselines give similar estimates."
            )

# --- Every strike day, ranked --------------------------------------------------------------
st.subheader("Per-event diagnostic ratios")
dates = da.per_event_diagnostics()
dates["day"] = pd.to_datetime(dates["date"]).dt.strftime("%d %b %Y")

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
    "Diagnostic only — each bar is a rigor-produced event-level system actual/expected ratio, "
    "not the certified ADR-0009 median station-day headline. The cited strike seed is unchanged."
)

# --- Where the demand landed ---------------------------------------------------------------
st.subheader("Where the extra bikes were hired, station by station")
options = dates.sort_values("date", ascending=False)
picked = st.selectbox(
    "Pick a strike day",
    options["date"].astype(str).tolist(),
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
        "Diagnostic only — each bar is one station's observed deviation from its weather-adjusted "
        "baseline for the selected event. It is not the certified ADR-0009 headline."
    )
