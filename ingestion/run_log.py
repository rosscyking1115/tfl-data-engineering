"""Append one observability row per successful daily run (rigor-pass Area 5).

The run-metadata table IS the audit trail: what the pipeline ingested and when, readable by
the Streamlit "Pipeline health" page and by any reviewer straight from the repo. Failures
don't reach this log — they surface as red runs + an auto-opened GitHub issue, and as gaps
the coverage test reports.

Run at the end of the daily job:  python ingestion/run_log.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "app" / "gold_export"
LOG = EXPORT / "run_log.parquet"


def main() -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    bp = pd.read_parquet(EXPORT / "live_bikepoint.parquet")
    ls = pd.read_parquet(EXPORT / "live_line_status.parquet")
    state = json.loads((EXPORT / "journey_ingest_state.json").read_text(encoding="utf-8"))
    daily = pd.read_parquet(EXPORT / "daily_journey_stats.parquet")

    row = pd.DataFrame([{
        "run_ts": datetime.now(timezone.utc).isoformat(),
        "snapshot_date": today,
        "bikepoint_rows": int((bp["snapshot_date"] == today).sum()),
        "line_status_rows": int((ls["snapshot_date"] == today).sum()),
        "snapshot_days_collected": int(ls["snapshot_date"].nunique()),
        "journey_max_extract": int(state["max_extract"]),
        "journey_max_date": str(pd.to_datetime(daily["date_day"]).max().date()),
        "dbt_build": "pass",  # this step only runs after the gated dbt build succeeded
    }])
    if LOG.exists():
        row = pd.concat([pd.read_parquet(LOG), row], ignore_index=True)
    row.to_parquet(LOG, index=False)
    print(f"[OK] run_log: {len(row)} rows (appended {today})")


if __name__ == "__main__":
    main()
