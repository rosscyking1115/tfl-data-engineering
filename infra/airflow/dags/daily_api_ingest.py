"""Local Airflow demonstration: ingest a dated API snapshot, then await dbt.

The loader owns idempotency (replace per snapshot_date), so a manual re-run or
backfill is safe. GitHub Actions remains the durable runtime for this workflow.
"""

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator
from alert_utils import DEFAULT_ARGS

with DAG(
    dag_id="daily_api_ingest",
    schedule="30 5 * * *",
    start_date=datetime(2026, 7, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["tfl", "incremental", "local-demo"],
) as dag:

    ingest = BashOperator(
        task_id="pull_and_load_snapshots",
        bash_command="python /repo/ingestion/daily_api_ingest.py --date {{ ds }}",
    )

    trigger_dbt = TriggerDagRunOperator(
        task_id="trigger_dbt_build",
        trigger_dag_id="dbt_build_and_test",
        wait_for_completion=True,
        allowed_states=["success"],
        failed_states=["failed"],
    )

    ingest >> trigger_dbt
