# ADR-0011: Add a bounded reliability-reference extension

- **Status:** Accepted
- **Date:** 2026-07-16
- **Gate 0 result:** NARROW; accepted by Ross on 2026-07-16

## Context

The living workflow already proves a Spark backfill, plain-Python increments, dbt models, daily
snapshots, and an honest historical/live boundary (ADR-0006). Its retained 2022–May 2026 source
window also contains five ordered CSV header variants and an observed partial boundary date.

Those observations are useful outside the app only if they are expressed as a small portable
contract with licence-safe fixtures, deterministic replay semantics, and an independent oracle.
Raw excerpt publication and managed-platform proof remain unresolved.

## Decision

Add `benchmark/gate0` as a bounded reliability-reference extension:

- keep one public seam: `run_case(engine, case_definition)`;
- separate `schema_family` from exact `header_variant_id`;
- publish constructed fixtures for the five verified variants, not raw TfL rows;
- define exact duplicate, whole-period replacement, incompatible rejection, and London DST rules;
- require DuckDB/Spark semantic parity against committed expected outputs;
- keep Databricks optional and validate-only.

This extension does not alter the Streamlit app, daily scheduler, runtime storage, or accepted
ADRs. ADR-0006's living-workflow and historical/live honesty boundary remain authoritative.

## Consequences

### Positive

- source-adapter and recovery behavior becomes independently executable;
- observed incidents cannot be confused with constructed stress cases;
- cross-engine drift is visible through canonical rows and state hashes;
- the contribution remains free and useful without a managed platform.

### Negative

- fixtures and goldens become reviewed contract surface;
- raw-source representativeness remains limited to 148 retained files;
- licence uncertainty blocks raw excerpts;
- Databricks feasibility remains unverified until an authorized local profile exists.

## Follow-up gate

Ross accepted the `NARROW` result on 2026-07-16. T2 may begin after Gate 0 receives an independent
Reviewer/QA pass and merges. Acceptance authorizes adaptation of the portable reference only; it
does not authorize archive downloads, raw publication, managed deployment, a release, or novelty
claims.
