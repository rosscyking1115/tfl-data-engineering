# ADR-0003: Orchestration sizing and the incremental-layer boundary

- **Status:** Accepted
- **Date:** 2026-07-08

## Context

Phase 3 needed an orchestrator and a daily incremental layer. Two decisions had a
"do the impressive thing" option and a "do the honest thing" option, and this project's
whole thesis is that the honest thing, documented, is worth more.

## Decision 1: Airflow standalone, not a Celery/Postgres fleet

`airflow standalone` in a single container (scheduler + webserver + SQLite metadata DB),
one `docker-compose.yml` service. Three small DAGs for a single-user pipeline do not need
CeleryExecutor, a Postgres metadata DB, or worker autoscaling.

- **Why not the full fleet:** it would look more "production" in a screenshot, but it
  adds moving parts that this workload never exercises — the same sizing-theatre the Spark
  decision (ADR-0002) rejects. The README's limitations section states exactly what would
  change under real concurrency (LocalExecutor/Celery on Postgres, secrets backend, real
  on-call webhook), which is more valuable than pretending to have built it.
- **dbt in an isolated venv inside the image** (`/home/airflow/dbt-venv`): dbt-core and
  Airflow conflict on shared transitive deps; isolating dbt is the standard, reliable fix
  and mirrors how teams actually run dbt under Airflow.

## Decision 2: the daily increment is plain Python, and that IS the boundary

[`ingestion/daily_api_ingest.py`](../../ingestion/daily_api_ingest.py) uses `requests` +
`snowflake-connector` `executemany` — no Spark, no dbt-for-ingestion. A day's snapshot is
~800 dock rows + ~20 line rows. The loader:

- lands raw JSON as bronze before any parsing (replayable),
- enforces ingestion quality gates (partial API response → fail loudly, don't load a
  half-empty snapshot),
- is idempotent via delete+insert per `snapshot_date` (safe reruns/backfills).

This is the deliberate counterweight to the Spark backfill: the README's honesty-boundary
section only lands because both halves exist in the same repo and the reasoning for each
is symmetric — *the data size dictates the tool, in both directions.*

## Consequences

- Failure alerting is shared across all DAGs via one `on_failure_callback`
  (`dags/alert_utils.py`) and was **demonstrated** with a deliberate-failure DAG, not just
  wired up.
- `monthly_history_check` re-lists the bulk bucket and fails if new journey files appear —
  turning "extend the backfill" into an automated nudge rather than a memory.
- The whole orchestrated daily run (loads + full dbt build + 48 tests) costs ~0.15
  credits; cumulative build cost ≈0.50 credits (~$1) of the $400 trial.
