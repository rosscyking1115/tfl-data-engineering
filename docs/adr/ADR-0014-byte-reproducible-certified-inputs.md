# ADR-0014 — Byte-reproducible inputs for the ADR-0009 certificate

## Context

The ADR-0009 certificate pins the SHA-256 of its input Parquet so a consumer cannot silently
re-derive the headline number. That is only a contract if rebuilding those inputs produces
the same bytes. It did not.

DuckDB writes external Parquet in plan-dependent row order. Running
`dbt build --select +tag:analytics` locally reordered rows without changing a single value,
which changed the file hashes and turned `test_tcert` red. A reader then could not tell a
real regression from reordering noise — the failure mode that most damages a project whose
whole value is that its evidence is trustworthy.

Measured on 2026-07-27, before the fix:

| Export | Byte-stable across 3 builds? |
|---|---|
| `demand_deviation` | yes (coincidence of its plan) |
| `demand_deviation_ml` | no |
| `disruption_events` | no |
| `expected_demand` | no |

All four were **set-identical** across every build — verified with an order-independent
fingerprint (row count plus a commutative sum of per-row hashes). No data ever changed.

Two further facts came out of the investigation, and they cut in opposite directions:

- The **certified payload was already order-independent.** Shuffling 1,282,472 input rows and
  re-running `analysis/rigor.py` left `headline`, `placebo`, `sensitivity` and `spatial`
  byte-identical, and `certified_result_sha256` unchanged. The statistical claim was never
  at risk.
- The **per-event diagnostics were not.** `per_event_cis` bootstraps by drawing array
  *positions*, so with the same seed a different input order resamples different stations.
  Those CIs moved under a pure reordering. They are deliberately excluded from the certified
  payload, so no claim was affected — but a diagnostic that wobbles is reporting plan noise
  as uncertainty.

## Decision

Fix the root cause, and make any future failure legible.

**Deterministic writes.** Every external export ends with an explicit `ORDER BY` over its
grain key. An `ORDER BY` only yields a *total* order if the key is unique, so each key is
also asserted unique by a dbt test — `demand_deviation`, `demand_deviation_ml` and
`expected_demand` gained one; `disruption_events` already had it. The ordering is therefore
self-policing rather than assumed.

This was preferred over certifying a canonical sorted form. Hashing a canonical
representation would also have worked, but it costs the certificate its strongest property:
that a consumer can verify by hashing the file they are holding, with no tooling and no
trust in ours. Fixing the writer keeps that property instead of working around its absence.

**Legible failure.** Schema 1.1 additionally pins an order-independent
`input_content_fingerprint` per Parquet input, covered by the certificate ID like every
other field. Validation still fails on a byte mismatch — the strict contract is unchanged —
but it can now distinguish `row-order drift, not a data change` from `content changed`.
The first names a determinism regression; the second is a real evidence change.

**Order-independent diagnostics.** `per_event_cis` sorts within each event day before
resampling, so the diagnostic CIs are reproducible too.

## Consequences

Verified after the change: three consecutive full rebuilds produced **byte-identical**
artefacts for all four exports, and a full `dbt build` now leaves the committed certificate
valid, where before it invalidated it.

No certified number moved. `headline`, `placebo`, `sensitivity` and `spatial` are unchanged
and `certified_result_sha256` is identical to the pre-fix value — the 1.42× result, its
95% CI 1.24–1.61, the placebo and the sensitivity battery all stand exactly as certified.
`per_event` values changed once, by design, and are stable from now on.

The certificate ID changed (`tcert-adr0009-ba640c07c2bb` → `tcert-adr0009-36085ec85fec`)
because the inputs are re-sorted and the schema gained a field. The four export Parquet
files change once, in row order only.

`tests/test_determinism.py` guards the fix: every external export must end in a top-level
`ORDER BY` over a dbt-proven unique key, the export set is pinned so a new export must
choose an order key deliberately, and both bootstraps are asserted invariant to input row
order. The static checks need PyYAML, which is added to the CI job.
