"""Failure alerting shared by all DAGs: POST to ALERT_WEBHOOK_URL if configured
(Slack-compatible payload), and always log CRITICAL so the alert is provable
from the task log alone."""

import logging
import os
from datetime import timedelta

import requests

log = logging.getLogger("tfl.alerts")


def notify_failure(context) -> None:
    ti = context["task_instance"]
    msg = (
        f":rotating_light: TfL pipeline failure — dag={ti.dag_id} task={ti.task_id} "
        f"run={context['run_id']} try={ti.try_number}"
    )
    log.critical(msg)
    url = os.getenv("ALERT_WEBHOOK_URL")
    if url:
        try:
            requests.post(url, json={"text": msg}, timeout=10)
            log.critical("alert webhook delivered")
        except requests.RequestException as exc:
            log.critical("alert webhook FAILED to deliver: %s", exc)


DEFAULT_ARGS = {
    "owner": "tfl",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": notify_failure,
}
