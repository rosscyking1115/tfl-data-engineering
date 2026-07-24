"""Build + test dbt after the local ingest demonstration completes.

This DAG is intentionally trigger-only: GitHub Actions is the durable scheduler.
dbt runs from its isolated venv (see Dockerfile).
"""

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator
from alert_utils import DEFAULT_ARGS

with DAG(
    dag_id="dbt_build_and_test",
    schedule=None,
    start_date=datetime(2026, 7, 1),
    catchup=False,
    max_active_runs=1,
    default_args=DEFAULT_ARGS,
    tags=["tfl", "dbt", "local-demo"],
) as dag:

    BashOperator(
        task_id="dbt_build",
        bash_command=(
            "/home/airflow/dbt-venv/bin/dbt build "
            "--project-dir /repo/dbt --profiles-dir /repo/dbt"
        ),
    )
