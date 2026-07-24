"""Monthly: re-list the TfL bulk bucket and fail (-> alert) if new journey files
have appeared that the backfill hasn't processed — the nudge to extend silver."""

import csv
import subprocess
from datetime import datetime
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
from alert_utils import DEFAULT_ARGS

INVENTORY = Path("/repo/docs/gate0/cycle_file_inventory.csv")


def check_for_new_files() -> None:
    before = sum(1 for _ in INVENTORY.open()) - 1
    subprocess.run(
        ["python", "/repo/ingestion/gate0_cycle_inventory.py"], check=True
    )
    with INVENTORY.open(encoding="utf-8") as f:
        after = sum(1 for _ in csv.reader(f)) - 1
    print(f"bucket objects: {before} -> {after}")
    if after > before:
        raise RuntimeError(
            f"{after - before} new file(s) in the TfL bucket — extend the backfill"
        )


with DAG(
    dag_id="monthly_history_check",
    schedule="@monthly",
    start_date=datetime(2026, 7, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["tfl", "bulk"],
) as dag:

    PythonOperator(task_id="compare_bucket_inventory", python_callable=check_for_new_files)
