# Gate 0 decision: NARROW

## Decision

**NARROW — retain the portable, constructed reliability-reference contribution; do not claim a
raw-source benchmark or managed proof.**

This is the terminal T1 result. The evidence remains useful without Databricks, Streamlit, or the
daily application workflow. Ross accepted this decision and its narrower claim on 2026-07-16.
T2 may proceed after this Gate 0 change receives an independent Reviewer/QA pass and merges.

## Baseline and cutoffs

| item | recorded value |
|---|---|
| baseline branch | remote `main` fast-forwarded before branch creation |
| baseline commit | `ef2a7fee29dd64f1e48fb737cad1011232eb036d` |
| implementation branch | `feat/reliability-gate0` |
| historical listing | 482 objects; retained `docs/gate0/cycle_file_inventory.csv`; newest modification 2026-06-09T13:50:19Z |
| refreshed listing | 482 objects observed 2026-07-16T00:29:19Z; no added, removed, or metadata-changed keys |
| retained byte evidence | 148 CSVs / 6,466,686,539 bytes / 2022–May 2026 window |
| landscape and licence cutoff | 2026-07-16 UTC |
| cross-engine run | 2026-07-16T00:33:56Z |

The refreshed 482 count is a new observation with a cutoff. It does not turn the earlier inventory
into a live guarantee.

## Evidence resolved

- SHA-256, exact ordered-header fingerprint, and Phase 1 reconciliation are present for all 148
  retained files. Non-retained hashes and row counts are explicitly empty.
- Five ordered header variants are verified: 36 + 1 classic and 100 + 8 + 3 nextgen files.
  Quoted and unquoted serialization of the 100-file nextgen order is one parsed-header variant.
- Reconciliation remains 41,376,421 raw = 41,376,181 silver + 240 quarantine, with zero per-file
  delta.
- The missing end-station identifier, two reordered nextgen headers, and **3 locally observed
  2026-06-01 starts beyond extract 444's 2026-05-31 filename end** are observed incidents.
- The full retained backfill found zero duplicate rental IDs. Duplicate replay, correction,
  incompatible replacement, and DST ambiguity are labelled constructed.
- DuckDB 1.5.4 and containerized Spark 4.0.1 produced identical canonical rows,
  reconciliation, and state hashes in all five cases.

## Acceptance result

| test | result | evidence |
|---|---|---|
| explain listing differences | PASS | no difference; both counts and cutoffs retained in `listing-comparison.json` |
| hash all 148 retained files | PASS | `source-incident-inventory.csv` |
| represent all verified variants safely | PASS | five constructed representative fixtures; no raw rows |
| verify fixture bytes and sidecars | PASS | pytest provenance checks |
| separate observed and constructed incidents | PASS | sidecars, inventory, and contribution contract |
| duplicate replay invariant | PASS | exact hash replay leaves state unchanged |
| correction invariant | PASS | constructed correction replaces its complete declared period |
| incompatible replacement invariant | PASS | prior state and hash remain unchanged |
| DuckDB/Spark semantic parity | PASS | five cases in `cross-engine-results.json` |
| preserve app and live data | PASS | no application, daily workflow, state, or live snapshot diff |
| Databricks validation | NARROW — unverified | no CLI/profile; no remote action attempted |
| raw-excerpt licence gate | NARROW — blocked | TfL terms grant feed rights but Gate 0 did not prove that this public S3 archive is registered feed Information |

## Licence decision

TfL's Transport Data Service terms allow copying, publication, distribution, adaptation, and
commercial/non-commercial use of licensed Information with required attribution. They separately
prohibit automated extraction from Santander Cycles website pages absent written permission. The
terms page does not, by itself, prove that this anonymous public S3 archive is one of the feeds
covered by a registration.

Therefore Gate 0 publishes metadata, hashes, constructed rows, and derived outputs only. Raw
source excerpts remain blocked. Every relevant artifact carries the required TfL, OS, and Geomni
attribution plus a non-endorsement statement. The repository MIT licence remains code-only.

## Accepted claim

> A compact, licence-bounded compatibility and replay case suite derived from five ordered header
> variants observed across 148 locally retained TfL Cycle Hire files. Constructed fixtures prove
> deterministic duplicate, replacement, rejection, DST, and DuckDB/Spark conformance behavior.

## Forbidden claims

- Do not call the suite complete, exhaustive, production-certified, or representative of all 482
  historical objects.
- Do not claim genuine duplicate, correction, or incompatible-replacement source incidents.
- Do not claim raw TfL rows are licensed for republication under MIT or CC0.
- Do not claim Databricks validation, deployment, execution, teardown, performance, or Free
  Edition reliability.
- Do not claim first, only, novel, Kaggle-ready, Hugging Face-ready, released, or leaderboard-ready.

## T2 handoff

Ross accepted `NARROW` on 2026-07-16. T2 may consume the accepted seam, schema mapping,
constructed fixture policy, state invariants, expected outputs, and exclusions after Gate 0
merges. T2 must keep raw excerpts blocked, re-run its own comparator/licence cutoffs, and treat
managed validation as optional until an authorized validate-only profile exists.
