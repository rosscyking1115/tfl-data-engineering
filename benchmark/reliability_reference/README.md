# Portable reliability reference 0.2.0

This is a compact, licence-bounded compatibility and replay case suite derived from five ordered
header variants observed across 148 locally retained TfL Cycle Hire files. Constructed fixtures
prove deterministic duplicate, replacement, rejection, DST, recovery, and DuckDB/Spark
conformance behavior.

It is deliberately separate from the Streamlit app, daily workflow, ingestion state, and live
Parquet. It downloads no source data, needs no credentials, and writes only to an explicit local
workspace. It is not a raw TfL benchmark, managed-platform proof, performance comparison, release,
or production runtime.

## Run it

```text
python -m benchmark.reliability_reference validate
python -m benchmark.reliability_reference run --engine duckdb --scenario all --output <dir>
python -m benchmark.reliability_reference run --engine spark --scenario all --output <dir>
python -m benchmark.reliability_reference compare --duckdb <dir> --spark <dir> --output <dir>
python -m benchmark.reliability_reference compare-managed --reference <duckdb-dir> --managed <delta-export-dir> --output <dir>
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

`workspace=None` creates a disposable directory. Explicit workspaces inside committed fixtures,
contracts, or expected outputs are rejected. The runner never imports application state and does
not perform automatic garbage collection; deleting an old workspace is an explicit caller action.

## Contract

- Only five exact ordered-header fingerprints are accepted across `classic` and `nextgen`.
- Row identity is `(schema_family, rental_id)`; identifiers remain strings and duration is integer
  milliseconds.
- Source timestamps become offset-aware `Europe/London` values. Ambiguous and nonexistent local
  times reject the complete object; UTC is not derived.
- Invalid values, truncated inputs, unknown headers, and ownership violations reject the complete
  object. Row quarantine is reserved and remains zero.
- Non-correction ownership periods cannot overlap active objects, and `(schema_family, rental_id)`
  must remain unique across the complete active state.
- DuckDB performs typed CSV reads, parsing, and validation in SQL. Spark uses an explicit typed
  schema plus DataFrame expressions and windows. Only contract/state orchestration and comparison
  are shared; Europe/London DST fold validation is implemented independently in each adapter.
- State hashes cover compact, sorted-key UTF-8 JSON with explicit nulls and canonical row order.
- JSON under `expected/` is the human-readable oracle. Parquet is an interoperability artifact and
  is compared after decoding, never byte-for-byte.

## Optional managed candidate

`infra/databricks/reliability_reference/` contains a temporary, uniquely scoped Free Edition
bundle candidate. It has no local `delta` CLI engine: an authenticated Databricks Spark session
must call the unexported `run_managed_case` entry point. The bundle sync allowlist contains only
contracts, expected JSON, constructed fixtures, scenarios, and managed code. Its cleanup job can
drop only five validated table names; bundle destruction then removes the uniquely named schema,
volume, and jobs.

This lane does not supersede the portable oracle or the GitHub Actions/Parquet/DuckDB application
runtime. Its current evidence state is documented under
[`docs/reliability-reference/releases/0.3.0/`](../../docs/reliability-reference/releases/0.3.0/).

See [replay semantics](../../docs/reliability-reference/replay-semantics.md),
[fixture provenance](../../docs/reliability-reference/fixture-provenance.md), and
[limitations](../../docs/reliability-reference/limitations.md).
