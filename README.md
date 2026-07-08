# London Cycle-Hire Analytics Platform

End-to-end data platform over the public **Santander Cycle Hire** archive: a decade of
messy, multi-format journey files unified into a tested warehouse model and served through
an interactive app — with a flagship analysis of **how transport disruptions reshape
cycling demand** across London.

**[▶ Live demo](https://share.streamlit.io/)** · [Engineering notes](docs/) · [Architecture](#architecture)

> [!NOTE]
> Built as a rigorous, honestly-scoped portfolio project. Each tool is used only where the
> data justifies it, and every non-obvious decision is recorded as an [ADR](docs/adr/).

## Overview

Transport for London publishes every cycle-hire journey since 2012 — roughly **189M trips
across 482 files**, with formats and schemas that drift wildly between years. This project
turns that raw archive into a clean, queryable, tested analytical layer, then puts a live
dashboard on top.

The headline question it answers: **when the Tube is disrupted, how much extra demand lands
on the cycle network, and where?** Strike days in the data drive **1.2×–2.6× normal cycling
demand** — an effect this platform quantifies per station against a weather-adjusted baseline.

## Highlights

- **Real scale, real mess.** A PySpark backfill unifies **41.4M journeys (2022–2026)** across
  five distinct file schemas — columns renamed, dropped, and re-ordered between eras — with
  per-file reconciliation proving no rows are silently lost.
- **The right tool for each job.** Spark for the multi-era backfill; plain Python for the
  kilobyte-sized daily API pulls. Both rationales are documented — see
  [the Spark ↔ Python boundary](#the-sparkpython-boundary).
- **Tested, dimensional model.** A dbt star schema (`fact_journey`, `dim_station`, `dim_date`)
  with **48 data tests**, including cross-era station-identity conforming.
- **Orchestrated & observable.** Airflow DAGs for daily ingestion, model builds, and a
  demonstrated failure-alerting path.
- **Interactive & AI-queryable.** A Streamlit app for exploration, plus a read-only MCP
  server exposing the warehouse to AI clients through typed, guardrailed tools.
- **Frugal by design.** The entire warehouse build cost **~$1** on an XS warehouse with
  aggressive auto-suspend.

## Architecture

```mermaid
flowchart TD
    A[cycling.data.tfl.gov.uk<br/>bulk history · 482 files] -->|PySpark backfill| S[(Warehouse<br/>silver · 41.4M journeys)]
    API[TfL Unified API<br/>BikePoint + Line Status] -->|Python daily loader| S
    W[Open-Meteo<br/>weather] --> S
    S --> D{dbt<br/>models + 48 tests}
    D --> G[(Gold star schema<br/>+ demand-deviation)]
    G --> APP[Streamlit app]
    G --> MCP[MCP server]
    AF[[Airflow]] -.orchestrates.-> API
    AF -.orchestrates.-> D
```

Medallion layers: **bronze** (files/JSON as landed) → **silver** (typed, deduped, era-unified)
→ **gold** (tested star schema + analytical models).

## The Spark/Python boundary

The most deliberate decision in the project. **Spark is justified** for the backfill: ~189M
rows across 482 files with five incompatible schemas is genuinely awkward on a single machine,
and Spark's positional CSV reader would silently corrupt the re-ordered columns without
per-variant, by-name projection. **Spark would be theatre** for the daily increment: a day of
BikePoint + Line Status JSON is a few hundred rows, handled by ~150 lines of `requests` +
`executemany`. The same reasoning that *requires* Spark for one job *forbids* it for the other.
See [ADR-0002](docs/adr/ADR-0002-spark-in-docker-and-header-variants.md).

## Tech stack

| Layer | Tool |
|---|---|
| Batch processing | PySpark (Dockerised) |
| Warehouse | Snowflake (build) → DuckDB + Parquet (durable, free) |
| Transformation & tests | dbt |
| Orchestration | Airflow · GitHub Actions |
| App & AI access | Streamlit · Model Context Protocol |
| Enrichment | TfL Unified API · Open-Meteo |

## Quickstart

```bash
python -m venv .venv
.venv/Scripts/pip install -r app/requirements.txt      # demo app deps
streamlit run app/streamlit_app.py                      # runs on committed Parquet, no warehouse needed
```

The demo app reads committed Parquet via DuckDB — it needs no database and runs fully offline.
To reproduce the warehouse build (Spark → Snowflake → dbt), see [docs/](docs/).

## Project structure

```
ingestion/   API loaders, warehouse loaders, data-export scripts
spark/       multi-era backfill job
dbt/         staging + marts models, tests, seeds
app/         Streamlit app (DuckDB over committed gold Parquet)
mcp/         read-only MCP server over the gold layer
infra/       Airflow (Docker Compose), run scripts
docs/        ADRs, architecture and engineering notes
```

## Engineering notes

- [ADR-0001](docs/adr/ADR-0001-dataset-and-stack.md) — dataset selection, with measured evidence
- [ADR-0002](docs/adr/ADR-0002-spark-in-docker-and-header-variants.md) — Spark environment & schema-drift handling
- [ADR-0003](docs/adr/ADR-0003-orchestration-and-boundary.md) — orchestration sizing & the incremental boundary
- [ADR-0004](docs/adr/ADR-0004-mcp-readonly-boundary.md) — MCP read-only guardrails
- [ADR-0005](docs/adr/ADR-0005-streamlit-demo-layer.md) — the demo layer & durable hosting

## Roadmap

The platform is evolving into a **continuously-updating disruption-intelligence workflow**:
a daily GitHub Actions job ingests live Line Status and dock occupancy, refreshes a
weather-adjusted demand baseline via dbt-duckdb, and surfaces — live — which corridors are
absorbing displaced demand during a disruption. Journey data is published in bulk with a lag,
so the design honestly separates **historical quantification** from **live monitoring** rather
than claiming real-time trip prediction.
