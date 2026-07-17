# TfL Data-Engineering Pipeline — Build Plan (Claude Code handoff)

## 0. What this is (read first, it governs everything)

A **skill-credential project**, not a product. Its entire job is to make this interview
sentence true:

> "I built an end-to-end pipeline on ~80M+ rows of real TfL data — here's why Spark for the
> backfill and why plain Python for the daily increments, here's the star schema and dbt
> tests, here's the orchestration, and here's what Snowflake cost me and how I tuned it."

Rules inherited from the discussion:
- **Time-boxed: 2–3 weekends to a working end-to-end slice.** Then document and STOP.
- No users, no accounts, no product framing, no streaming theatre.
- Every tool used only where the data justifies it, with the "why-not" written down —
  the documented restraint is worth as much as the tool use.
- This project deliberately carries Snowflake + Spark; the housing and aerospace projects deliberately do NOT.
  Keep that separation clean.

## 1. Gate 0 — verify BEFORE locking the dataset (do this first, ~1 evening)

Two live candidates. Do not commit to either from research alone — pull real samples and
compare on facts, same discipline as every other gate in this project.

| Check | Option A — Cycle hire | Option B — Air quality + live commute |
|---|---|---|
| Bulk backbone | cycling.data.tfl.gov.uk journey files since 2015 | LAQN (King's College/GLA/TfL) hourly readings since 1990s |
| Claimed scale | ~80–100M rows (from public case studies) | large, multi-decade, **row count not yet verified — verify in this gate** |
| Personal relevance to Ross | none (never used the bikes) | direct (bus/Tube commuting + air quality both actually used/cared about) |
| Messiness | confirmed: format drift, schema drift, station-ID quirks across years | plausible: sites online/offline over decades, unit/standard changes, sensor gaps — **confirm with real files** |
| Live/incremental layer | BikePoint + line status (bolt-on, not personally used) | bus/Tube line status + arrivals + crowding (the part Ross would actually query) |

**Gate 0 tasks:**
1. Download 2–3 sample cycle-hire history files across different years; confirm format
   drift firsthand; estimate true full-history row count from file sizes.
2. Pull LAQN's historical archive/API for 2–3 sites across the longest available date range;
   get a real row count and confirm the messiness (gaps, site changes, unit shifts).
3. Write the verdict as an ADR: which one is the Spark-justifying backbone, or — if both
   check out — whether combining a smaller LAQN pull as *enrichment* onto Option A is better
   than treating LAQN as its own primary (avoid the two-genre-in-one-project dilution problem
   from earlier plans).
4. **Only after this gate produces real numbers does Section 2 onward get finalized** against
   the winning option. Placeholders below assume Option A pending this check; swap freely.

**On live/streaming data — why groups 2–6 (line status, arrivals, crowding, BikePoint) are
NOT the Spark-justifying backbone, addressed directly:** it's not that live data is small —
Instagram/Airbnb prove live data can be huge. It's huge there because millions of users have
generated events continuously for years, and *time × producers* is what accumulates volume,
not "liveness" itself. TfL's live feeds are pull-based snapshots of a few thousand vehicles/
stations — polling them only accumulates volume **from the moment you start polling**, and a
2–3 weekend build has no way to backfill years of history the way a published bulk archive
already has. So live feeds stay in the plan, just in their honest role: a **secondary,
smaller streaming/incremental demonstration** running alongside whichever bulk archive wins
Gate 0 — not competing for the "big dataset" job, because the job needs pre-accumulated
history and live feeds structurally can't supply that on this timeline.

## 2. Dataset (pending Gate 0 — placeholder assumes Option A)

**Primary — historical Santander Cycle Hire journeys (batch backbone):**
Public bucket at cycling.data.tfl.gov.uk, per-journey records since 2015
(rental id, bike id, start/end station + timestamps, duration). Scale is genuinely
Spark-class: 10M+ journeys/year, 41M in 2018–2021 alone → full history roughly
**80–100M+ rows across hundreds of files**. Critically for the portfolio story, the
historical files are **authentically messy**: formats and properties are inconsistent
across years (CSV, XML, XLS mixes; schema/name drift; station-ID quirks like the
`BikePoint_` prefix). That mess is a feature — it's the cleaning story worth telling.

**If Gate 0 selects Option B instead:** swap the backbone to LAQN's historical air-quality
archive, keep the same medallion shape (§2 below), and change the live/incremental layer to
bus/Tube line status + arrivals + crowding (personally relevant, still all-mode). Star schema
becomes `fact_air_reading` (site × pollutant × hour) joined to `dim_site`, `dim_date`, with a
`fact_line_status_snapshot` from the incremental layer — sketch properly once Gate 0 confirms
real LAQN volume.

**Secondary — TfL Unified API (the refreshing/orchestration story):**
Register a free app key at api.tfl.gov.uk. Daily incremental pulls of **BikePoint**
(dock status/capacity per station) and **Line Status** (JSON). This gives orchestration a
real recurring job and shows API ingestion alongside bulk files.

**Optional enrichment (only if time allows):** daily weather (Met Office/Open-Meteo) joined
by date — proven combination in this domain, adds one clean cross-source join.

**Honest caveat (state it, don't hide it):** TfL cycling data appears in some existing
portfolio pipelines (mostly GCP/BigQuery ones). It is far less saturated than NYC TLC, and
this build differentiates on: the modern stack (Spark + Snowflake + dbt + orchestrator),
medallion + tested models, the batch-plus-incremental split, quality gates, and the
documented why/why-not reasoning. Do not claim novelty; claim rigor.

## 3. Architecture (medallion)

*(Note: section numbers from here on are one ahead of a strict re-count after the Gate 0
insert above — treat headings as sequential markers, not exact indices.)*

```
cycling.data.tfl.gov.uk (bulk history)      TfL Unified API (daily JSON)
            │                                        │
            ▼                                        ▼
   object storage / local "raw" zone   ←──  ingestion + quality checks
            │  (bronze: files as-landed, immutable)
            ▼
   PySpark backfill transform  ──────►  Snowflake
   (schema unification across years,     bronze → silver (clean, typed, deduped)
    dedupe, typing, station-ID fixes)            → gold (star schema)
            │                                        │
            ▼                                        ▼
        dbt models + tests  ──────────►  fact_journey, dim_station, dim_date,
   (silver→gold in-warehouse, ELT)        dim_weather?, bikepoint_daily_snapshot
            │
            ▼
   Orchestrator (see §4) — scheduled daily API pull + monthly file check + dbt build + tests
            │
            ▼
   Power BI dashboard (PL-300 tie-in): usage trends, station flows, strike/weather effects
```

## 3. The Spark ↔ DuckDB honesty boundary (interview gold — implement AND document)

- **Backfill (Spark, justified):** unifying ~10 years of inconsistent multi-format files at
  80M+ rows is genuinely awkward on a single machine at full grain — partitioned Spark job
  (partition by year/month), schema-mapping layer per era of file format, bad-record handling
  (quarantine table, not silent drops).
- **Daily increments (plain Python/DuckDB, justified):** a day's BikePoint/status JSON is
  tiny. Using Spark for it would be theatre. Small typed loader → Snowflake stage.
- Write BOTH rationales in the README. This split is the single most interview-valuable
  artifact in the project.

## 4. Tool decisions (locked, with reasons)

- **Orchestrator: Airflow.** Deliberate contrast with the housing and aerospace projects (Dagster) → the
  portfolio then shows range across both major orchestrators, and Airflow remains the most
  job-spec-listed. DAGs: `daily_api_ingest`, `monthly_history_check`, `dbt_build_and_test`,
  with failure alerts (email/Slack webhook). Run via Docker Compose or Astronomer free tier.
- **Warehouse: Snowflake** ($400/30-day trial — plan the build inside that window; note
  auto-suspend, XS warehouse, and record actual credit burn in the README as the cost story).
  Frame honestly: chosen to build warehouse fluency; the README's why-not notes when
  DuckDB/BigQuery would be the right production call at this scale.
- **Transform: dbt** (silver→gold models, ~5–8 models max), tests: unique/not_null keys,
  accepted ranges (duration > 0, dates in range), relationship tests station→dim.
- **Quality at ingestion:** row-count drift vs expected, schema-drift detection per file era,
  duplicate rental-id check, unknown-station quarantine. (Great-Expectations-style; plain
  pytest checks are acceptable — the CHECKS matter, not the brand.)
- **BI: Power BI** on the gold layer (ties directly to PL-300).
- **Repo:** single repo, `infra/` (compose, orchestrator), `spark/`, `dbt/`, `ingestion/`,
  `docs/` (architecture diagram, ADRs, cost notes, why/why-not).

## 5. Phases (each ends in a working state)

- **Phase 0 (evening):** TfL API key, Snowflake trial, repo scaffold, ADR-0001 (dataset +
  stack rationale). Download 2–3 sample history files, confirm the mess firsthand.
- **Phase 1 (weekend 1):** Spark backfill for 2–3 recent years end-to-end into Snowflake
  silver. Quarantine path working. Row counts reconciled and recorded.
- **Phase 2 (weekend 2):** dbt star schema + tests green. Ingestion quality checks wired.
  Extend backfill toward full history if credits/time allow.
- **Phase 3 (weekend 2–3):** Airflow DAGs live (daily API pull + dbt build), one deliberate
  failure alert demonstrated. Power BI dashboard on gold.
- **Phase 4 (final evening):** README as the product — architecture diagram, the honesty
  boundary section, cost notes, limitations, "what I'd change under real concurrency."
- **DONE means:** one full-history (or ≥3-year) backfill + scheduled daily increment + tested
  star schema + one dashboard + the documented reasoning. Anything beyond is scope creep.

## 6. Optional Phase 5 — MCP layer (bonus, only after DONE)

**Honest placement:** MCP is not part of a data pipeline (Airflow orchestrates it, not an
AI). The genuine, modern use here: **expose the gold layer to an AI client** so Claude can
answer natural-language questions over the warehouse ("which stations gained the most usage
after 2022?") via typed tools instead of guessed SQL.

- Options: use an existing **Snowflake MCP server** (official/community implementations
  exist — verify current state at build time), or write a **small read-only MCP server**
  with the Python SDK exposing 3–4 curated query tools over gold views.
- Guardrails: read-only Snowflake role scoped to gold; no DDL/DML tools; label it in the
  README as an AI-integration demonstration on top of the pipeline, not pipeline machinery.
- Value: one tasteful "AI-adjacent data engineering" differentiator few DE portfolios have.
  Time-box: one evening. If it fights you, cut it — the pipeline stands alone.

## 7. Pairing + non-goals

- **Cert pairing (separate from the build):** SnowPro Core (warehouse story) or Databricks
  Spark Developer Associate (processing story) — pick whichever matches target job specs.
  Badge passes filters; this project passes interviews.
- **Non-goals:** Kafka/streaming (no honest need here), multi-cloud, a web app, users,
  any "product" framing, extending past the time-box.

## 8. Claude Code instructions

Work phase by phase; each phase must end runnable. Keep secrets in `.env` (never committed).
Record every non-obvious decision as a short ADR. If a step balloons (e.g. full-history
backfill too slow/costly), shrink scope (3 years is fine) rather than extending the
time-box — the credential is the end-to-end rigor, not the row count.
