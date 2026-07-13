# Review-readiness pass

The six questions a rigorous data-team reviewer asks, each answered with evidence in this repo
(the closing gate of the rigor pass, 2026-07-13).

## 1 · Is the analytical claim honest?

**Yes — scoped as associational, with the assumptions written down.**
[ADR-0009](adr/ADR-0009-analytical-contract.md) states the estimand (1.42× median, 95% CI
1.24–1.61, 13 events), the event-study design, two independent baseline families, each
assumption as a falsifier, and a **correction log**: a citation audit found the January 2024
"strikes" were called off and removed them — the headline *changed* (1.33→1.42) because the
evidence did. Every event row carries a `source_url`
([disruption_dates.csv](../dbt/seeds/disruption_dates.csv)).

## 2 · Is data quality real or decorative?

**Real — the tests catch injected errors and caught a live incident.**
63 dbt data tests + a de-dup unit test + 36 pytest guards, including injected-error fixtures
(corrupt payloads, schema drift, truncated volume) that fail loudly
([test_pipeline_guards.py](../tests/test_pipeline_guards.py),
[test_journey_increment.py](../tests/test_journey_increment.py)). The freshness tripwire,
configured during the pass, immediately surfaced a real 3-day outage; the reconciliation test
caught the arrival-spillover subtlety on its first run.

## 3 · Does it fail loudly and recover?

**Yes.** Every gate raises (`SystemExit`) rather than degrading silently; dbt tests gate
delivery in the daily job; a red run auto-opens a GitHub issue; API calls retry with backoff;
every write is idempotent (run-twice tests). The one *irrecoverable* failure mode — a missed
daily snapshot — is mitigated (tripwire + catch-up) and displayed honestly: 2026-07-11/12 were
lost to a since-fixed crash and appear as permanent holes on the **Pipeline health** page.

## 4 · Can I reproduce it?

**Yes, at three depths.** (a) The app: clone → `pip install -r app/requirements.txt` →
`streamlit run app/streamlit_app.py` — everything runs on committed Parquet. (b) The pipeline
in seconds: `make sample-run` exercises the real gates/aggregation on a committed 1,500-row
extract excerpt. (c) In full: the [Makefile](../Makefile) targets, pinned requirements, seeded
(deterministic) statistics, and the Spark backfill runbook in [docs/](.). Secrets are
documented in `.env.example`, never committed.

## 5 · Is it maintainable?

**Yes.** Layered dbt with lineage ([static dbt docs](dbt/index.html)); engine-portable SQL with
the differences isolated in three macros; ten ADRs recording *why*
([decision log](adr/)); [source contracts](source_contracts.md) naming exactly what each
upstream field the pipeline depends on; CI (ruff + pytest) on every PR.

## 6 · Was the migration designed-in?

**Better — it was executed, then verified.** The serving layer moved to committed
Parquet + DuckDB before the trial mattered; the full dbt DAG then ported with an **exact
reconciliation** against the Snowflake-era gold (41,376,181 fact rows) as the migration test.
[ADR-0010](adr/ADR-0010-migration-retrospective.md) records what the plan predicted, what
actually happened, and what that taught.
