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

# --- Headline: the whole story in two numbers -------------------------------------------
head = da.disruption_headline()
rigor = da.rigor_results()
if not head.empty:
    ratios = {r["day_type"]: r for _, r in head.iterrows()}
    normal = ratios.get("Normal days")
    disr = ratios.get("Disruption days")
    hl = rigor.get("headline", {})
    with st.container(horizontal=True):
        if normal is not None:
            st.metric(
                "A normal day", f"{normal['median_ratio']:.2f}× demand", border=True,
                help=f"Baseline median across {int(normal['n_dates'])} normal days",
            )
        if disr is not None:
            uplift = (disr["median_ratio"] - 1) * 100
            ci = (f"95% CI {hl['ci95_lo']:.2f}–{hl['ci95_hi']:.2f}×"
                  if hl else f"median across {int(disr['n_dates'])} disruption days")
            st.metric(
                "A strike day", f"{disr['median_ratio']:.2f}× demand",
                delta=f"{uplift:+.0f}% vs normal", border=True,
                help=f"{ci} · cluster bootstrap over event days (ADR-0009)",
            )
    cap = ("Read as a multiple of normal: **1.00× = exactly expected**, so 1.42× means 42% "
           "more cycling than a comparable non-strike day.")
    if hl:
        cap += (f" The 95% confidence interval is **{hl['ci95_lo']:.2f}–{hl['ci95_hi']:.2f}×** "
                f"(bootstrap over the {hl['n_events']} event days).")
    st.caption(cap)

    st.caption(
        ":material/balance: **This is an observed association, not a causal claim.** Strike "
        "days are compared with a weather-adjusted normal under stated assumptions "
        "([the analytical contract](https://github.com/rosscyking1115/tfl-data-engineering/blob/main/docs/adr/ADR-0009-analytical-contract.md))."
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
    "Blue = more cycling than normal; the dashed red line is a normal day. Every full network "
    "strike lifts demand. The near-baseline days are a stations-only partial action "
    "(25 Nov 2022) and a residual knock-on day. "
    "Each event is source-cited in the repo; a citation audit removed two January 2024 dates "
    "whose strike was called off."
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
        "normal. The largest increases are around Tube interchanges and business districts."
    )
