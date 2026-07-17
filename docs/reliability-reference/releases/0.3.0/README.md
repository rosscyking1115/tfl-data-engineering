# T3 managed-proof candidate

This directory contains redacted evidence from the optional `0.3.0` candidate. The portable
DuckDB/Spark `0.2.0` suite remains the supported release.

Current gate: **NARROW: managed execution unavailable**. Three Free Edition serverless job
invocations, split across the initial deployment and one allowed corrective deployment, failed
before scenario code started. The task runner could not reliably read workspace Python files. No
complete managed attempt reached the semantic oracle, so there is no DuckDB-versus-Delta
comparison. The redacted [managed report](managed-proof.json) records the decision.

The temporary schema contained no tables. The cleanup task hit a separate script-wrapper context
error, after which bundle destruction removed the managed volume, schema, both jobs and workspace
files. Independent checks confirmed that every scoped resource was absent.

## Release decision

- `PASS`: `0.3.0` may be proposed after independent review and owner approval.
- `NARROW` or `FAIL`: retain the diagnostics, leave this candidate unreleased and release `0.2.0`.
  **This is the selected path.**
- `STOP`: block every release until cleanup and secret handling are resolved.

The `0.2.0` release builder permits later prose corrections but compares every portable
implementation, contract, fixture and oracle file byte-for-byte with frozen T2. It also excludes
this unreleased `0.3.0` evidence directory from the `0.2.0` archive.

See the [claim ledger](claim-ledger.json), [managed report](managed-proof.json) and
[prepared portfolio copy](portfolio-copy.md). None of the portfolio copy is published by T3.

![Portable-to-managed recovery flow](portable-managed-recovery.svg)

![Candidate conformance matrix](conformance-matrix.svg)
