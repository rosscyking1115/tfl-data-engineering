# Review-readiness pass

This review closed the rigor pass on 2026-07-13. It checks six questions against evidence in the
repository.

## 1 · Is the analytical claim honest?

Yes. [ADR-0009](adr/ADR-0009-analytical-contract.md) defines the result as an association and
states its assumptions. It records the estimate (1.42× median, 95% CI
1.24–1.61, 13 events), the event-study design, two independent baseline families, each
assumption as a falsifier, and a **correction log**: a citation audit found the January 2024
"strikes" were called off and removed them. The headline changed from 1.33× to 1.42× after that
correction. Every event row carries a `source_url`
([disruption_dates.csv](../dbt/seeds/disruption_dates.csv)).

## 2 · Is data quality real or decorative?

Yes. The suite has 63 dbt data tests, a de-duplication unit test and 36 pytest guards. Its
injected-error fixtures cover corrupt payloads, schema drift and truncated volume, and fail loudly
([test_pipeline_guards.py](../tests/test_pipeline_guards.py),
[test_journey_increment.py](../tests/test_journey_increment.py)). The freshness tripwire,
configured during the pass, immediately surfaced a real 3-day outage; the reconciliation test
caught the arrival-spillover subtlety on its first run.

## 3 · Does it fail loudly and recover?

Yes. Every gate raises (`SystemExit`) instead of continuing with degraded data; dbt tests gate
delivery in the daily job; a red run auto-opens a GitHub issue; API calls retry with backoff;
every write is idempotent (run-twice tests). A missed daily snapshot is irrecoverable. The
freshness tripwire and catch-up job reduce that risk. The app displays missed dates: 2026-07-11/12
were lost to a since-fixed crash and appear as permanent holes on the **Pipeline health** page.

## 4 · Can I reproduce it?

Yes. The app runs from committed Parquet after `pip install -r app/requirements.txt` and
`streamlit run app/streamlit_app.py`. `make sample-run` exercises the actual gates and aggregation
on a committed 1,500-row extract. The full path uses the [Makefile](../Makefile), pinned
requirements, seeded statistics and the Spark backfill runbook in [docs/](.). Secrets are
documented in `.env.example`, never committed.

## 5 · Is it maintainable?

Yes. The repository has layered dbt models with lineage ([static dbt docs](dbt/index.html)) and
engine-portable SQL with differences isolated in three macros. Eleven ADRs record decisions
([decision log](adr/)). [Source contracts](source_contracts.md) name the upstream fields the
pipeline uses, and CI runs Ruff and pytest on every pull request.

## 6 · Was the migration designed-in?

It was executed and verified. The serving layer moved to committed Parquet and DuckDB before the
trial expired. The full dbt DAG then moved with an **exact
reconciliation** against the Snowflake-era gold (41,376,181 fact rows) as the migration test.
[ADR-0010](adr/ADR-0010-migration-retrospective.md) records what the plan predicted, what
actually happened, and what that taught.
