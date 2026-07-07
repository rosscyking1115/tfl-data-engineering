# Project rules (from the governing plan — docs/tfl-data-engineering-plan.md)

- **Skill-credential project, time-boxed to 2–3 weekends.** No users, no accounts, no
  product framing, no streaming theatre. When a step balloons, shrink scope (3 years of
  data is fine) — never extend the time-box.
- **Every phase must end runnable.** Don't leave a phase half-wired.
- **Secrets live in `.env`** (never committed). `.env.example` documents the shape.
- **Record every non-obvious decision as a short ADR** in `docs/adr/`.
- **Dataset is locked** (ADR-0001): cycle-hire journey archive is the Spark backbone;
  LAQN is cut; TfL Unified API (BikePoint + Line Status) is the daily incremental layer;
  weather (Open-Meteo) is the optional enrichment.
- **The honesty boundary is the product:** Spark only for the multi-era backfill, plain
  Python/DuckDB for daily increments — both rationales belong in the README.
- Snowflake trial (30 days) starts at Phase 1 weekend, not before. Use XS warehouse +
  auto-suspend; record actual credit burn in the README.
- Stack is locked: PySpark, Snowflake, dbt, Airflow, Power BI. Don't add tools.

## Environment

- Windows 11; venv at `.venv` (`.venv\Scripts\python.exe`), deps: requests, duckdb,
  pandas, openpyxl (PySpark added in Phase 1).
- Set `PYTHONIOENCODING=utf-8` when a script prints DuckDB tables (cp1252 console).
- Bulk bucket listing: `https://s3-eu-west-1.amazonaws.com/cycling.data.tfl.gov.uk/`
  (ListObjectsV2; the vanity domain serves an HTML browser, not XML).
