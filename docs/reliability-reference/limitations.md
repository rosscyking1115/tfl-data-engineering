# Limitations and forbidden claims

The suite runs without Streamlit, Databricks or another managed platform. Its scope is narrow:

- It covers five ordered header variants verified across 148 retained files from 2022 through May
  2026, not every historical object or future schema.
- Fixtures are constructed. Duplicate replay, corrections, incompatible replacements, malformed
  rows, and DST ambiguity are conformance scenarios, not claimed TfL source incidents.
- It is not exhaustive, production-certified, performance-tested, security-certified or a
  replacement for operational ingestion controls.
- It proves local DuckDB and pinned-container Spark semantic parity, not Databricks deployment,
  managed execution, service reliability, or SLA behavior.
- It publishes no raw source excerpts and makes no Kaggle, Hugging Face, PyPI, leaderboard,
  first, only or novelty claim.
- ODCS, dbt contracts, DuckLake, OpenLineage, and Databricks were not selected for T2 because the
  compact portable contract did not establish a requirement that justified them.

The suite does not alter the accepted boundary in ADR-0006: the living workflow remains the daily
application path; this reference is offline audit and conformance evidence.
