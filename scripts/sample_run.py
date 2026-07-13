"""`make sample-run` — the whole increment path on a committed 1,500-row sample, in seconds.

A reviewer shouldn't need a 10-year download to see the pipeline work: this runs the real
schema gate, dedupe, aggregation and reconciliation logic (ingestion/journey_increment.py)
on samples/journeys_sample.csv (a genuine excerpt of TfL extract 444 — Powered by TfL Open
Data) and prints what would be upserted.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ingestion"))

import journey_increment as ji  # noqa: E402

flows, daily = ji.aggregate_file(ROOT / "samples" / "journeys_sample.csv")

print(f"sample parsed: {int(daily['journeys'].sum()):,} journeys "
      f"over {daily['date_key'].nunique()} day(s), {flows['station_key'].nunique()} stations")
print("\ndaily_journey_stats rows that would be upserted:")
print(daily.to_string(index=False))
print("\ntop 5 station-day flows:")
print(flows.sort_values("departures", ascending=False).head(5).to_string(index=False))
print("\n[OK] schema gate, dedupe, aggregation and reconciliation all exercised on the sample.")
