# Project rules

> **Direction changed (2026-07-08, ADR-0006):** this evolved from a one-off DE pipeline
> into a **living disruption-aware cycling-demand workflow**. The original build plan is
> kept for history at `docs/tfl-data-engineering-plan.md`; the rules below now govern.

- **Still not commercial:** no users, no accounts, no auth, no billing. It's a
  genuinely-running portfolio workflow, not a product to sell.
- **Durable + free is the constraint.** The live runtime is GitHub Actions (public repo) +
  committed Parquet + DuckDB — no dependency on a live warehouse. Snowflake is a
  **documented past phase** (the batch build), not a runtime; Airflow is a **local
  showcase**, not the durable scheduler.
- **The honesty boundary is still the product:** Spark for the multi-era backfill, plain
  Python/DuckDB for the kilobyte increments. And journey data lags ~1–2 months, so the
  workflow honestly separates **historical quantification** from **live monitoring** — never
  claim real-time trip prediction (ADR-0006).
- **Every phase ends runnable.** Secrets in `.env` (never committed). Record non-obvious
  decisions as a short ADR in `docs/adr/`. Never add AI attribution to commits.
- **Dataset** (ADR-0001): cycle-hire journey archive (Spark backbone); LAQN cut; TfL Unified
  API (BikePoint + Line Status) the live layer; weather (Open-Meteo) now built, not optional.
- **Working stack:** PySpark (backfill), Snowflake (past build), dbt + dbt-duckdb,
  Airflow (local), DuckDB + Parquet (durable), Streamlit (public app), GitHub Actions
  (runtime), MCP (AI access), LightGBM + MLflow + FastAPI (demand forecast — ADR-0008,
  local/free). Power BI is optional PL-300 practice.

## Environment

- Windows 11; venv at `.venv` (`.venv\Scripts\python.exe`), deps: requests, duckdb,
  pandas, openpyxl, pyspark, snowflake-connector-python, python-dotenv, dbt-snowflake,
  dbt-duckdb, pyarrow, streamlit, altair, mcp. ML layer (separate `ml/requirements.txt`):
  lightgbm, mlflow, scikit-learn, holidays, fastapi, uvicorn.
- Set `PYTHONIOENCODING=utf-8` when a script prints DuckDB tables (cp1252 console).
- Bulk bucket listing: `https://s3-eu-west-1.amazonaws.com/cycling.data.tfl.gov.uk/`
  (ListObjectsV2; the vanity domain serves an HTML browser, not XML).
