"""Deliberate failure for demonstrating the alert path (plan §5: 'one deliberate
failure alert demonstrated'). Trigger manually; the task raises, the
on_failure_callback fires, and the CRITICAL alert line lands in the task log
(plus the webhook if ALERT_WEBHOOK_URL is set)."""

from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator

from alert_utils import DEFAULT_ARGS


def blow_up() -> None:
    raise RuntimeError("deliberate failure: alerting-path demonstration")


with DAG(
    dag_id="failure_alert_demo",
    schedule=None,
    start_date=datetime(2026, 7, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["tfl", "demo"],
) as dag:

    PythonOperator(task_id="deliberately_fail", python_callable=blow_up)
