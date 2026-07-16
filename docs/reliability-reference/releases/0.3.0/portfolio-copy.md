# Prepared portfolio copy — do not publish from this workflow

## Website

Built a licence-bounded reliability-reference suite using constructed fixtures and a reviewed
semantic oracle. The portable `0.2.0` suite verifies deterministic replay, replacement, rejection,
and interruption recovery across DuckDB and a digest-pinned Spark 4.0.1 container. The optional
Databricks statement must be added only if the managed gate ends in `PASS`.

## CV

- Designed a constructed-fixture conformance suite for deterministic replay and atomic recovery,
  with exact DuckDB/Spark semantic parity and fault injection at three publication boundaries.
- Optional after managed `PASS`: validated the same oracle once on bounded Databricks serverless
  Delta, then exported redacted evidence and verified targeted teardown.

## LinkedIn

The awkward part of ingestion is rarely the happy path. I turned five years of observed header
drift into a small constructed test pack that asks harder questions: what happens when an object is
replayed, corrected, malformed, or interrupted immediately before publication? DuckDB and pinned
Spark now have to agree on every decoded row, disposition, reconciliation event, and state hash.

Do not imply that the constructed incidents occurred in TfL data. Do not mention Databricks parity
unless the committed managed report records `PASS` and verified teardown.
