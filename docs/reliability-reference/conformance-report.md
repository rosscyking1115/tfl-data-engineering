# Candidate conformance report

Version 0.2.0 executes ten scenarios: five verified header variants, duplicate replay, a new
period, correction, late arrival/order independence, header rejection, invalid/truncated/ownership
overlap/state-identity/DST rejection, three interruption hooks with retry in both engines, and
incremental-versus-clean rebuild, plus incompatible-replacement rejection with prior-state
preservation.
Scenario 010 declares the complete cross-engine comparison.

Local candidate evidence on 2026-07-16:

| Lane | Result | Scope |
|---|---:|---|
| DuckDB | PASS | all 10 executable scenarios against committed JSON oracle |
| Spark 4.0.1, digest pinned | PASS | all 10 executable scenarios plus all 3 interruption/retry hooks against the same oracle |
| DuckDB/Spark comparison | PASS | canonical rows, history, reconciliation, dispositions, and final state hash |
| Databricks Delta candidate | PENDING | no profile, deployment, execution, resource, cost, or managed claim yet |

The state hashes are deterministic across engines and across late-arrival, retry, uninterrupted,
and clean-rebuild paths. CI regenerates reports as artifacts; generated reports are not committed.
This is candidate evidence pending the independent Reviewer/QA gate recorded by the project process.
