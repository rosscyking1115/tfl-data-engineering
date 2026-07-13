# ADR-0010: Snowflake→DuckDB migration — how it actually happened (retrospective)

- **Status:** Accepted (retrospective)
- **Date:** 2026-07-13

## Context

The plan was classic designed-in migration: keep dbt SQL portable, land Parquet from day one,
then swap the adapter when the Snowflake trial neared its end. What actually happened was more
interesting, and worth recording honestly because the *result* exceeds the plan.

## What actually happened (three moves, not one swap)

1. **Gold-export first (2026-07-08, ADR-0005/0006).** Rather than swapping the adapter, the
   durable runtime was built by **exporting the gold rollups to committed Parquet** and pointing
   everything user-facing (Streamlit, the assistant, MCP, the analytics dbt layer, Power BI) at
   those files via DuckDB. The warehouse became optional for the product months before the trial
   ended — the strongest form of migration-readiness: *migration as a non-event*.
2. **Evidence capture (2026-07-10..13).** Because the warehouse itself would vanish, its facts
   were banked while alive: [snowflake_evidence.md](../snowflake_evidence.md) (41.4M silver rows,
   gold sizes, ~1-credit cost) and the **hourly station rollup**
   (`app/gold_export/hourly/`, 19.5M rows) that exists nowhere else.
3. **Full-DAG port (2026-07-13, rigor pass C3).** Finally the classic swap: staging + marts run
   on `dbt build --target duckdb` over the local silver Parquet, with engine differences isolated
   in [macros/portability.sql](../../dbt/macros/portability.sql) (three macros + one conditional
   date spine). **Verification: the DuckDB rebuild reconciles with the Snowflake-era gold
   exactly** — 41,376,181 fact rows / 1,282,472 flows / 1,616 days / 856 stations — and the same
   53 data tests pass on both engines.

## What made it cheap (confirming the design bets)

- **Parquet as the interchange format** (Spark wrote silver as Parquet; gold exported as
  Parquet) — DuckDB read everything natively, zero data movement.
- **dbt as the seam** — the port touched 8 SQL files, mostly `to_number(to_char(...))`-class
  spelling differences; the *logic* moved unchanged, and the tests came along for free as the
  migration verifier.
- **Config-driven targets** — the Snowflake profile remains, inert, as documented history.

## What the plan didn't predict

- The two snapshot sources needed a **shape-normalizing staging layer** (the Snowflake-era
  loader tables and the durable snapshots differ in columns/types) — sources aren't as
  swap-clean as models.
- DuckDB needed **memory tuning** for the 41M-row fact on a busy workstation
  (`memory_limit: 4GB`, `preserve_insertion_order: false`, file-backed spill; and
  `temp_directory` must NOT be set via dbt-duckdb settings — it can't be re-`SET` per thread).
- The migration order inverted: product first, pipeline second. That inversion is the lesson —
  **exporting the serving layer beats swapping the warehouse** when the goal is durability.
