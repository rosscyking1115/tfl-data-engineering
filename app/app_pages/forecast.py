"""Station demand forecast and counterfactual baseline (ADR-0008)."""

import altair as alt
import data_access as da
import streamlit as st

st.title("Station demand forecast")
st.caption(
    "A LightGBM model learns each station's daily departures from calendar, weather, "
    "recent-demand lags and the disruption flag. Predicting with the flag **off** estimates "
    "normal demand more accurately than the previous median-by-bucket baseline "
    "([ADR-0008](https://github.com/rosscyking1115/tfl-data-engineering/blob/main/docs/adr/ADR-0008-ml-demand-forecast.md))."
)

acc = da.forecast_accuracy()
if not acc.empty:
    r = acc.iloc[0]
    lift = 100 * (r["median_mae"] - r["ml_mae"]) / r["median_mae"] if r["median_mae"] else 0
    with st.container(horizontal=True):
        st.metric("Model error (MAE)", f"{r['ml_mae']:.2f}", border=True,
                  help="Mean absolute error of the learned baseline, departures/day")
        st.metric("Median-baseline error", f"{r['median_mae']:.2f}", border=True,
                  help="The previous weather-adjusted median baseline")
        st.metric("Improvement", f"{lift:.0f}% lower error", border=True,
                  help=f"across {int(r['n']):,} station-days")
    st.caption(
        "On the held-out 2026 window, the model cut error by **~21% versus the median** and "
        "**~28% versus a seasonal-naive baseline**. Validation was temporal, not random."
    )

st.subheader("Predicted vs actual")
stations = da.station_names()
default = stations.index("Hyde Park Corner, Hyde Park") if "Hyde Park Corner, Hyde Park" in stations else 0
station = st.selectbox("Station", stations, index=default)

series = da.forecast_series(station)
if series.empty:
    st.info("No forecast data for this station.")
else:
    base = alt.Chart(series).transform_fold(
        ["actual", "predicted"], as_=["series", "departures"]
    ).mark_line().encode(
        x=alt.X("date_day:T", title=None),
        y=alt.Y("departures:Q", title="Departures / day"),
        color=alt.Color("series:N", title=None,
                        scale=alt.Scale(domain=["actual", "predicted"],
                                        range=["#2563eb", "#f59e0b"])),
        tooltip=["date_day:T", "series:N", alt.Tooltip("departures:Q", format=".0f")],
    )
    strikes = series[series["is_disruption"]]
    layers = base
    if not strikes.empty:
        rules = alt.Chart(strikes).mark_rule(color="#ef4444", opacity=0.35).encode(x="date_day:T")
        layers = base + rules
    st.altair_chart(layers, width="stretch")
    st.caption(
        "Orange shows expected normal demand and blue shows actual demand. Red lines mark known "
        "disruption dates."
    )

st.subheader("What drives the model")
imp = da.feature_importance()
if imp.empty:
    st.info("Feature importances unavailable (run ml/train.py).")
else:
    bar = alt.Chart(imp.head(12)).mark_bar(color="#2563eb").encode(
        x=alt.X("gain_pct:Q", title="Importance (% of total gain)"),
        y=alt.Y("feature:N", sort="-x", title=None),
        tooltip=["feature", alt.Tooltip("gain_pct:Q", format=".1f")],
    )
    st.altair_chart(bar, width="stretch")
    st.caption(
        "Recent-demand lags (`roll_7`, `roll_28`, `dep_lag_7`) and station identity carry most "
        "of the model gain. Weather and the disruption flag add smaller adjustments."
    )
