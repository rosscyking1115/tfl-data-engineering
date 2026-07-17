# Portable reliability reference 0.2.0

This licence-bounded suite tests compatibility, replay and recovery against five ordered-header
variants observed in 148 locally retained TfL Cycle Hire files. Its constructed fixtures cover
duplicate replay, replacement, rejection, daylight-saving transitions and DuckDB/Spark parity.

It is separate from the Streamlit app, daily workflow, ingestion state and live
Parquet. It downloads no source data, needs no credentials, and writes only to an explicit local
workspace. It is not a raw TfL benchmark, managed-platform proof, performance comparison or
production runtime.

## Run it

```text
python -m benchmark.reliability_reference validate
python -m benchmark.reliability_reference run --engine duckdb --scenario all --output <dir>
python -m benchmark.reliability_reference run --engine spark --scenario all --output <dir>
python -m benchmark.reliability_reference compare --duckdb <dir> --spark <dir> --output <dir>
```

Spark is pinned to an immutable Spark 4.0.1 image digest by `Makefile`, CI, and
`Run-Benchmark.ps1`. On Windows:

```powershell
benchmark\reliability_reference\Run-Benchmark.ps1 -Command All
```

The Python seam is:

```python
run_case(engine, case_definition, *, workspace=None, fault_at=None) -> RunResult
```

`workspace=None` creates a temporary directory. The runner rejects workspaces inside committed
fixtures, contracts or expected-output directories. It never imports application state or removes
old workspaces automatically; the caller decides when to delete one.

## Contract

- Only five exact ordered-header fingerprints are accepted across `classic` and `nextgen`.
- Row identity is `(schema_family, rental_id)`; identifiers remain strings and duration is integer
  milliseconds.
- Source timestamps become offset-aware `Europe/London` values. Ambiguous and nonexistent local
  times reject the complete object; UTC is not derived.
- Invalid values, truncated inputs, unknown headers and ownership violations reject the complete
  object. Row quarantine is reserved and remains zero.
- Non-correction ownership periods cannot overlap active objects, and `(schema_family, rental_id)`
  must remain unique across the complete active state.
- DuckDB performs typed CSV reads, parsing and validation in SQL. Spark uses an explicit typed
  schema plus DataFrame expressions and windows. Only contract/state orchestration and comparison
  are shared; Europe/London DST fold validation is implemented independently in each adapter.
- State hashes cover compact, sorted-key UTF-8 JSON with explicit nulls and canonical row order.
- JSON under `expected/` is the reviewed oracle. Parquet is an interoperability artifact and
  is compared after decoding, never byte-for-byte.

See [replay semantics](../../docs/reliability-reference/replay-semantics.md),
[fixture provenance](../../docs/reliability-reference/fixture-provenance.md), and
[limitations](../../docs/reliability-reference/limitations.md).
