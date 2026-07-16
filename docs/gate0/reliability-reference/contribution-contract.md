# Gate 0 contribution contract

## Accepted seam

```text
run_case(engine, case_definition) -> canonical rows, reconciliation, state hash
```

The seam reads only files under `benchmark/gate0/`. It does not import the Streamlit app, the
daily workflow, `journey_ingest_state.json`, DuckDB production-like state, or live Parquet files.

## Evidence vocabulary

- **Observed**: measured directly from a source object, listing, or retained pipeline evidence.
- **Derived**: deterministic calculation from observed evidence, such as a SHA-256 digest or row
  reconciliation.
- **Constructed**: synthetic bytes or behavior created to test a contract. It is never presented
  as a TfL incident.

The missing end-station identifier, ordered-header changes, and 3 starts on the 2026-06-01
boundary beyond extract 444's stated end date are observed. Exact duplicate replay, correction,
incompatible replacement, and DST ambiguity are constructed cases.

## Schema contract

- `schema_family` is `classic` or `nextgen`.
- `header_variant_id` is SHA-256 over the compact UTF-8 JSON array of **parsed ordered field
  names**. CSV quoting is intentionally excluded, so quoted and unquoted serialization of the
  same ordered header is one variant.
- Five ordered variants are verified across **148 locally retained CSVs covering 2022 through
  May 2026**: 36 classic standard, 1 classic missing end-station identifier, 100 nextgen
  standard, 8 nextgen names-first, and 3 nextgen interleaved.
- Duration is an integer number of milliseconds. Classic seconds are multiplied by 1,000.
- Rental, bike, and station identifiers are strings; leading zeroes are preserved.
- Empty strings normalize to explicit nulls. A station endpoint is valid when it has a code or a
  name.

The machine-readable mapping is
[`benchmark/gate0/contracts/schema-map.json`](../../../benchmark/gate0/contracts/schema-map.json).

## Source-time contract

TfL source timestamps are interpreted in `Europe/London`. Canonical timestamps are offset-aware
local values. Gate 0 does **not** derive a UTC canonical timestamp. A nonexistent local time is
rejected. A fall-back time with two possible offsets is rejected unless a later contract adds an
explicit fold indicator; guessing the earlier or later instant is forbidden.

## Replay and ownership contract

1. A content SHA-256 already applied is an exact duplicate; rows and state hash are unchanged.
2. A correction must name the object it supersedes and declare the identical inclusive ownership
   period. It validates in full before any state mutation.
3. A valid correction removes every prior row whose start date is in that period, then installs
   the new object atomically.
4. An incompatible header, invalid timestamp, invalid duration, or ownership mismatch rejects the
   whole object and preserves prior rows and state hash.
5. State hashes cover sorted canonical semantic rows, not engine-specific ordering or an
   ingestion-history side channel.

## Oracle

DuckDB 1.5.4 and containerized Spark 4.0.1 consume the same mapping, fixtures, and case definitions.
The comparison covers ordered canonical rows, reconciliation actions, and final state hash. The
five-case result is recorded in [cross-engine-results.json](cross-engine-results.json).

## Publication contract

Every fixture sidecar declares its evidence class, byte hash, header fingerprint, ownership
period, supersession relation, and publication decision. Raw source excerpts are forbidden until
the public S3 archive is proven to be Information covered by the registered TfL Transport Data
Service licence. See [licence-matrix.csv](licence-matrix.csv) and
[`benchmark/gate0/ATTRIBUTION.md`](../../../benchmark/gate0/ATTRIBUTION.md).
