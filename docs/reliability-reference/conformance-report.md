# Conformance report

Version 0.2.0 runs nine scenarios. They cover the five verified header variants, duplicate replay,
a new period, correction, late arrival and order independence, header rejection, invalid or
truncated objects, ownership overlap, duplicate state identity, daylight-saving rejection, three
interruption hooks with retry, and incremental state versus a clean rebuild. Scenario 010 records
the complete cross-engine comparison.

Local evidence recorded on 2026-07-16:

| Lane | Result | Scope |
|---|---:|---|
| DuckDB | PASS | all 9 executable scenarios against committed JSON oracle |
| Spark 4.0.1, digest pinned | PASS | all 9 executable scenarios plus all 3 interruption/retry hooks against the same oracle |
| DuckDB/Spark comparison | PASS | canonical rows, history, reconciliation, dispositions, and final state hash |

The state hashes match across engines and across late-arrival, retry, uninterrupted and
clean-rebuild paths. CI regenerates its reports as artifacts; generated reports are not committed.
Independent Reviewer/QA accepted this evidence before T2 was merged.
