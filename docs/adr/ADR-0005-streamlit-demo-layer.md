# ADR-0005: Streamlit demo as the public consuming layer

- **Status:** Accepted
- **Date:** 2026-07-08

## Context

The pipeline is rigorous but backend-only — "nothing to show" a hiring manager can click.
Research (2026 hiring guides) said a **zero-setup hosted demo** is the single highest-ROI
"showable" artifact for a data project, and named Streamlit as the default. It also warned
that fusing an ML/AI layer into this repo would read as a shallow bolt-on for DE roles —
so the demo must stay a thin *consuming* layer, not a new genre. Power BI (the planned
consuming layer) can't be shared publicly on the free tier, which blunts its value as the
public artifact.

## Decision

Add a small **Streamlit** app (`app/`) as the public consuming layer, alongside (not
instead of) Power BI. Two pages over the existing gold rollups: usage trends and station
explorer.

### Why this doesn't violate the "no web app" non-goal
The non-goal targets *product framing* — users, accounts, a thing pretending to be a
startup. A read-only analytics dashboard is the **same role Power BI already plays** in the
locked stack: a consuming layer on gold. It adds no auth, no writes, no users. Framed
honestly in the README as a portfolio demo, not a product.

### Why DuckDB + committed Parquet, not a live Snowflake connection
- **Trial independence:** the Snowflake trial suspends ~2026-08-06, after which queries are
  blocked. A demo wired to Snowflake would die with it. So gold rollups are exported to
  `app/gold_export/*.parquet` (`ingestion/export_gold_to_parquet.py`) and the app reads them
  via DuckDB — it runs forever with no warehouse.
- **Free hosting:** Streamlit Community Cloud runs a public-repo app for free; committed
  Parquet (9 MB, well under limits) needs no secrets or external DB.
- **Only rollups ship:** `daily_journey_stats`, `station_daily_flows`, `dim_station`,
  `dim_date` — never the 41M-row `fact_journey` (too big for git; the rollups exist for
  exactly this).

## Consequences

- The ML **demand-forecasting** extension stays a **separate future project** (breadth
  belongs across projects, per the research) — the Streamlit app is a viz layer, not ML.
- Adds Streamlit + Altair to the dev deps; `app/requirements.txt` pins them for Cloud.
- One manual step remains the user's: connecting the repo in Streamlit Community Cloud
  (a GitHub-authorize click), same hands-on posture as the Power BI dashboard.
