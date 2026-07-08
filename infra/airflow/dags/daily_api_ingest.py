"""Daily 05:30 London: pull BikePoint + Line Status via the plain-Python loader,
then trigger the dbt build. The loader itself owns idempotency (delete+insert
per snapshot_date), so backfills/re-runs are safe."""

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
    default_args=DEFAULT_ARGS,
    tags=["tfl", "incremental"],
) as dag:

    ingest = BashOperator(
        task_id="pull_and_load_snapshots",
        bash_command="python /repo/ingestion/daily_api_ingest.py --date {{ ds }}",
    )

    trigger_dbt = TriggerDagRunOperator(
        task_id="trigger_dbt_build",
        trigger_dag_id="dbt_build_and_test",
        wait_for_completion=False,
    )

    ingest >> trigger_dbt
