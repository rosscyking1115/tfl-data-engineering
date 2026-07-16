# TfL reliability-reference Gate 0

Gate 0 is a bounded feasibility spike, not a full benchmark. Its result is **NARROW**: retain the
portable constructed compatibility/replay suite; do not claim raw-source publication or managed
platform proof.

## What is here

- `contracts/schema-map.json`: two semantic schema families and five exact ordered-header variants;
- `fixtures/`: synthetic rows plus provenance sidecars for every verified variant and replay case;
- `cases/`: engine-neutral object sequences;
- `expected/`: reviewed DuckDB outputs;
- `spike/runner.py`: `run_case(engine, case_definition)`;
- `evidence/spark/`: containerized Spark outputs;
- `managed/`: an unexecuted Databricks validate-only bundle skeleton.

The audit, inventory, licence matrix, cross-engine report, and terminal decision are in
[`docs/gate0/reliability-reference`](../../docs/gate0/reliability-reference/).

## Run the portable cases

```powershell
.venv\Scripts\python.exe -m pytest tests\test_gate0_reliability.py tests\test_gate0_inventory.py
```

Regenerate DuckDB expected outputs only after reviewing a deliberate contract change:

```powershell
.venv\Scripts\python.exe -m benchmark.gate0.spike.generate_expected
```

Run the pinned Spark comparison:

```powershell
.\benchmark\gate0\run-spark-comparison.ps1
```

Refresh public listing metadata and re-hash existing retained files without downloading objects:

```powershell
.venv\Scripts\python.exe -m benchmark.gate0.spike.build_inventory --date YYYY-MM-DD
```

## Boundaries

The spike does not import or modify the Streamlit app, daily workflow, live Parquets, incremental
watermark, or a production-like database. Raw TfL source rows are not committed. Duplicate and
correction scenarios are constructed. Ambiguous London local times reject rather than silently
choosing a UTC instant.

See [ATTRIBUTION.md](ATTRIBUTION.md) before reusing artifacts. The repository MIT licence applies
to code only.
