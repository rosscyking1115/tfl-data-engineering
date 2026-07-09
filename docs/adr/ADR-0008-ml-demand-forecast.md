# ADR-0008: Learned demand baseline — LightGBM over the median, as a counterfactual

- **Status:** Accepted
- **Date:** 2026-07-09

## Context

The workflow's "expected demand" was a **coarse median** grouped by station × day-of-week ×
wet/cold (`expected_demand.sql`). It is honest but blunt: it can't use the trend, the calendar,
continuous weather, or a station's own recent demand, so the "normal" band it draws is wide —
which muddies the disruption signal measured against it. The next evolution (decided 2026-07-08,
in this repo — ADR-0006 lineage) is to replace that baseline with a **learned model**, deepening
the workflow's core rather than bolting on an unrelated feature. Everything needed is already in
the committed gold Parquet, so this stays **durable and free — no Snowflake, no deadline.**

## Decision

Train a **LightGBM** model of daily station-level departures and use it two ways: as a sharper
baseline for the disruption analysis, and as a genuine forecaster.

- **Grain: daily, station-level.** What `station_daily_flows` provides and what the disruption
  workflow needs. Hourly isn't in the committed Parquet (only an aggregated hour-of-week profile)
  and is deferred (would need a pre-Aug-6 Snowflake re-export).
- **`is_disruption` is a *feature*, and the baseline is the counterfactual.** One model is trained
  on all history with the strike flag as an input; the "normal expected demand" baseline
  (`ml/predict.py` → `predicted_demand.parquet`) is obtained by predicting with the **flag forced
  off**. This keeps the strike signal out of the baseline it's measured against — no leakage — and
  the same model forecasts. Features: calendar (dow, month, day-of-year, weekend, UK bank holiday),
  weather (temp, precip, rain, wind, code, wet/cold), and leakage-safe per-station demand lags
  (prev-day, same-dow-last-week, rolling 7/28-day means, all shifted ≥1 day).
- **Temporal validation, never random.** Train 2022→2024, early-stop on 2025, report held-out
  2026-YTD plus a month-by-month backtest. The L1 objective predicts the conditional *median* —
  robust to the strike tail and aligned with the "normal / expected" framing.
- **It had to beat two baselines to ship.** On the held-out 2026 window it cut MAE **~21% vs the
  median** and **~28% vs a seasonal-naive** (same station, same day-of-week, last week). Across all
  station-days the ML baseline's normal-day dispersion is ~30% tighter (IQR 0.30 vs 0.43) while
  known strike days still spike above 1.0 — a better signal-to-noise ratio for the disruption
  effect. Both deviation tables (`demand_deviation`, `demand_deviation_ml`) are kept for A/B.
- **LightGBM, not deep learning.** The market-standard, interpretable choice for tabular demand;
  gives per-feature importance and per-row SHAP contributions for the app and the API.
- **MLflow, local.** Runs tracked to a local SQLite store (`sqlite:///mlflow.db`, gitignored); the
  compact model artifact (`ml/model/lgbm.txt`) and feature importances **are committed**, so dbt,
  the app, and the API run without retraining.
- **Serving: batch is primary, a local API is the demo.** `ml/predict.py` writes the committed
  Parquet the workflow consumes; `ml/serve.py` (FastAPI + a Dockerfile) exposes
  `GET /predict?station=&date=` returning the prediction + top SHAP factors. It is **runnable
  locally only — not deployed** (no paid/always-on hosting).

## Consequences

- The disruption analysis gets a sharper, defensible baseline, and the project gains a real,
  validated forecaster — same data, same domain, more depth.
- Retraining stays a **manual/periodic** step. The daily GitHub Action keeps ingesting live data
  and refreshing the deviation tables against the committed model; it does not retrain in the cron
  (that would need a heavier, less predictable job — out of scope for the free runtime).
- The model can't anticipate a strike's *magnitude* — deliberately. On strike days the API
  under-predicts actual demand, and that gap **is** the measured disruption effect.
- Category codes (station, weather_code) are stable only because every entry point rebuilds
  features from the same full Parquet via `build_dataset()`; a future move to on-the-fly single-row
  serving would need an explicit category mapping.

## Explicitly not in v1

Hourly grain, deep-learning/TFT, dock-availability forecasting (not backfillable — TfL publishes no
occupancy history, the same trap as Gate 0), always-on hosted inference, and automated retraining
in the scheduler.
