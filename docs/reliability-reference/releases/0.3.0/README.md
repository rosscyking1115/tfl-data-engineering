# T3 managed-proof candidate

This directory is the redacted evidence boundary for the optional `0.3.0` candidate. The portable
DuckDB/Spark suite at `0.2.0` remains authoritative and releasable independently.

Current gate: **PENDING OWNER AUTHENTICATION**. Databricks CLI 1.8.0 is installed and the bundle
parses through its local configuration before stopping at the expected missing-credentials check.
No Databricks resource has been deployed, no managed attempt has started, and no cost has been
incurred. `managed-proof.json` is intentionally absent until a terminal `PASS`, `NARROW`, `FAIL`,
or `STOP` decision exists.

The managed proof may use only constructed fixtures and a unique schema, volume, jobs, and five
Delta tables. Evidence must be exported and redacted before the targeted cleanup job and bundle
destruction. A `PASS` additionally requires independent absence checks after teardown.

## Release decision

- `PASS`: `0.3.0` may be proposed after independent review and owner approval.
- `NARROW` or `FAIL`: retain diagnostics, keep this candidate unreleased, and release `0.2.0`
  against the frozen T2 commit.
- `STOP`: block every release until cleanup and secret handling are resolved.

See the [claim ledger](claim-ledger.json), [managed evidence template](managed-proof.template.json),
and [prepared portfolio copy](portfolio-copy.md). None of the portfolio copy is published by T3.

![Portable-to-managed recovery flow](portable-managed-recovery.svg)

![Candidate conformance matrix](conformance-matrix.svg)
