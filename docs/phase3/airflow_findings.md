# Phase 3 findings — Airflow + daily increments (2026-07-08)

## Shape

Airflow 2.11 **standalone** in one container (infra/docker-compose.yml): scheduler +
webserver + SQLite metadata DB. Deliberately not the Celery/Postgres fleet — three
small DAGs for one user; the honest-sizing rule from the Spark decision applies to
orchestration too. dbt runs from an **isolated venv inside the image** because
dbt-core and Airflow famously conflict on shared dependencies (Dockerfile).

| DAG | schedule | what |
|---|---|---|
| `daily_api_ingest` | 05:30 Europe/London | plain-Python loader (BikePoint + Line Status → SILVER), then triggers dbt |
| `dbt_build_and_test` | 07:00 (safety net) + triggered | `dbt build` — all models + all tests |
| `monthly_history_check` | @monthly | re-lists the TfL bucket; fails loudly if new files appeared (→ extend backfill) |
| `failure_alert_demo` | manual | deliberately raises, to prove the alert path |

Failure alerting: every DAG shares `on_failure_callback` (dags/alert_utils.py) —
CRITICAL log line always; Slack-compatible webhook POST when `ALERT_WEBHOOK_URL` is set.

## Verification (2026-07-08, all via `airflow dags trigger` — not hand-run scripts)

1. **`daily_api_ingest` → success.** 798 bikepoint + 20 line-status rows for the day
   landed in SILVER (raw JSON in `data/raw/api/2026-07-08/`), then it triggered dbt.
2. **`dbt_build_and_test` (triggered run) → success: 48/48 PASS**, including the two
   Power BI rollups (`station_daily_flows` 1,282,472 rows; `daily_journey_stats` 1,616
   rows) — the full test contract now runs inside the orchestrator daily.
3. **`failure_alert_demo` → failed by design**, and the `on_failure_callback` fired:
   `CRITICAL - :rotating_light: TfL pipeline failure — dag=failure_alert_demo
   task=deliberately_fail ... try=1` in the task log. With `ALERT_WEBHOOK_URL` set the
   same payload POSTs to Slack.
4. All four DAGs parse with zero import errors; UI at http://localhost:8080.

Credit burn for the day's dbt builds + loads: ~0.15 credits (~$0.45).

## Ingestion quality gates

The daily loader refuses to load a partial snapshot (<700 bikepoints or <15 lines
fails the task → alert), and delete+insert on snapshot_date makes re-runs and
Airflow backfills idempotent.
