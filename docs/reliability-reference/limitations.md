# Limitations and forbidden claims

This contribution is useful without Streamlit, Databricks, or any managed platform, but its scope
is intentionally narrow.

- It covers five ordered header variants verified across 148 retained files from 2022 through May
  2026, not every historical object or future schema.
- Fixtures are constructed. Duplicate replay, corrections, incompatible replacements, malformed
  rows, and DST ambiguity are conformance scenarios, not claimed TfL source incidents.
- It is not exhaustive, production-certified, performance-tested, security-certified, or a
  replacement for operational ingestion controls.
- It proves local DuckDB and pinned-container Spark semantic parity. The optional T3 bundle may
  support one bounded Delta-conformance statement only after a committed managed `PASS` and
  independently verified teardown; it can never support service reliability or SLA claims.
- It publishes no raw source excerpts and makes no Kaggle, Hugging Face, PyPI, GitHub Release,
  leaderboard, first, only, or novelty claim.
- ODCS, dbt contracts, DuckLake, and OpenLineage were not selected because the compact portable
  contract did not establish a requirement that justified them. Databricks is an optional,
  temporary validation lane rather than a runtime dependency.

The suite does not alter the accepted boundary in ADR-0006: the living workflow remains the daily
application path; this reference is offline audit and conformance evidence.
