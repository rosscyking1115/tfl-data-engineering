# TfL Cycle-Hire Data Pipeline

End-to-end batch + incremental pipeline over the full Santander Cycle Hire journey
archive (**~189M rows, 482 files, 2012 → present**, measured in
[ADR-0001](docs/adr/ADR-0001-dataset-and-stack.md)): PySpark backfill of a decade of
schema-drifting bulk files into a Snowflake medallion warehouse, dbt-tested star schema,
Airflow orchestration of daily TfL API increments, Power BI on the gold layer.

## Architecture

```
cycling.data.tfl.gov.uk (bulk history)      TfL Unified API (daily JSON)
            │                                        │
            ▼                                        ▼
   raw zone (bronze: files as-landed)  ←──  ingestion + quality checks
            │
            ▼
   PySpark backfill transform  ──────►  Snowflake
   (3-era schema unification,            bronze → silver (clean, typed, deduped)
    dedupe, typing, station-ID fixes)           → gold (star schema)
            │                                        │
            ▼                                        ▼
        dbt models + tests  ──────────►  fact_journey, dim_station, dim_date,
   (silver→gold in-warehouse, ELT)        bikepoint_daily_snapshot
            │
            ▼
   Airflow — daily API pull + monthly file check + dbt build + tests
            │
            ▼
   Power BI dashboard: usage trends, station flows, weather/strike effects
```

## The Spark ↔ plain-Python honesty boundary

**Spark for the backfill** because the archive is genuinely hostile at scale: ~189M rows
across 482 files with five header variants (columns renamed, deleted, and re-ordered
between files — see [ADR-0002](docs/adr/ADR-0002-spark-in-docker-and-header-variants.md)),
requiring per-variant by-name projection, multi-format timestamp parsing, quarantine, and
a per-file reconciliation audit. The 2022→2026 slice (41.4M rows, 6.5 GB) unified in ~30
min on `local[10]` ([findings](docs/phase1/backfill_findings.md)).
**Plain Python for the daily increments** because a day of BikePoint/Line-Status JSON is
kilobytes; Spark there would be theatre. <!-- expand in Phase 3/4 -->

<!-- Phase 4: add the "when DuckDB alone would be the right production call" why-not. -->

## Cost notes (Snowflake)

<!-- Filled in Phase 2/4: actual credit burn, warehouse sizing, what tuning changed. -->

## Repo layout

- `ingestion/` — Gate 0 verification scripts, daily API loaders
- `spark/` — backfill job (Phase 1)
- `dbt/` — silver→gold models + tests (Phase 2)
- `infra/` — Docker Compose / Airflow (Phase 3)
- `docs/` — [governing plan](docs/tfl-data-engineering-plan.md), ADRs, Gate 0 evidence
- `data/` — local raw zone (gitignored)

## Setup

```powershell
python -m venv .venv
.venv\Scripts\pip install requests duckdb pandas openpyxl
copy .env.example .env   # then fill in keys
```

## Status

- [x] Gate 0 — dataset verified and locked ([ADR-0001](docs/adr/ADR-0001-dataset-and-stack.md))
- [x] Phase 1a — Spark backfill 2022→2026: 41.4M rows reconciled to parquet silver ([findings](docs/phase1/backfill_findings.md))
- [ ] Phase 1b — load silver into Snowflake (awaiting trial signup)
- [ ] Phase 2 — dbt star schema + tests
- [ ] Phase 3 — Airflow DAGs + Power BI
- [ ] Phase 4 — README as the product
