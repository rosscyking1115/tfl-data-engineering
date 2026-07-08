"""Build + test all dbt models. Normally triggered by daily_api_ingest; the
schedule below is a safety net so tests run at least daily even if the
ingest DAG is paused. dbt runs from its isolated venv (see Dockerfile)."""

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator

from alert_utils import DEFAULT_ARGS

with DAG(
    dag_id="dbt_build_and_test",
    schedule="0 7 * * *",
    start_date=datetime(2026, 7, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["tfl", "dbt"],
) as dag:

    BashOperator(
        task_id="dbt_build",
        bash_command=(
            "/home/airflow/dbt-venv/bin/dbt build "
            "--project-dir /repo/dbt --profiles-dir /repo/dbt"
        ),
    )
