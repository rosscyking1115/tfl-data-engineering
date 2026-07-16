# Candidate conformance report

Version 0.2.0 executes nine scenarios: five verified header variants, duplicate replay, a new
period, correction, late arrival/order independence, header rejection, invalid/truncated/ownership
and DST rejection, three interruption hooks with retry, and incremental-versus-clean rebuild.
Scenario 010 declares the complete cross-engine comparison.

Local candidate evidence on 2026-07-16:

| Lane | Result | Scope |
|---|---:|---|
| DuckDB | PASS | all 9 executable scenarios against committed JSON oracle |
| Spark 4.0.1, digest pinned | PASS | all 9 executable scenarios against the same oracle |
| DuckDB/Spark comparison | PASS | canonical rows, history, reconciliation, dispositions, and final state hash |

The state hashes are deterministic across engines and across late-arrival, retry, uninterrupted,
and clean-rebuild paths. CI regenerates reports as artifacts; generated reports are not committed.
This is candidate evidence pending the independent Reviewer/QA gate recorded by the project process.
