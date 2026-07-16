# Reliability-reference landscape audit

## Question and cutoff

Could a compact, public reference make TfL Cycle Hire source compatibility and object-replay
semantics independently testable without depending on this repository's Streamlit app or a
managed platform?

Search cutoff: **2026-07-16 UTC**. Searches were discovery aids, not proof of novelty. Repository
facts were checked against public GitHub pages or API metadata on the cutoff date.

## Recorded searches

| surface | exact query | result used |
|---|---|---|
| GitHub repository API | `TFL Santander Cycles schema evolution replay benchmark in:name,description,readme` | 0 repositories |
| GitHub repository API | `TFL cycle hire data pipeline schema drift in:name,description,readme` | 14 repositories; inspected the relevant TfL pipeline result |
| GitHub repository API | `data lake correction replay schema evolution benchmark in:name,description,readme` | 104 noisy results; no relevant open-data source-object reference in the first five |
| Web search restricted to GitHub | `tfl cycle hire journey data ingestion schema variants` | inspected `ropensci/bikedata` and TfL analytical projects |
| Web search restricted to GitHub | `data reliability benchmark schema evolution replay fixtures correction duplicate` | inspected executable benchmark and bad-data reference candidates |
| arXiv search | `data lake schema evolution benchmark replay` | inspected LST-Bench and *Create Benchmarks for Data Lakes* |

The detailed comparison is in [comparator-matrix.csv](comparator-matrix.csv). Search ranking is
not exhaustive, and absence from the result set is not evidence that no similar work exists.

## Finding

The adjacent work splits into three groups:

1. TfL import and analytics projects normalize historical files but do not publish an
   engine-neutral object-replay contract with state-preservation invariants.
2. General data-lake benchmarks exercise table formats and performance, not licence-bounded
   public-source incidents with fixture provenance.
3. Messy-data references describe duplicates and amendments but provide no executable oracle.

This supports a **bounded usefulness claim**, not a novelty claim: a small constructed fixture
suite can connect TfL-specific schema observations to deterministic replacement semantics and a
DuckDB/Spark oracle.

## Independent consumers

At least two workflows can consume the contribution without Streamlit or Databricks:

- a source-adapter CI workflow can run every observed ordered header through `run_case` and fail
  on silent positional mapping;
- an ingestion/recovery workflow can test duplicate, correction, and incompatible-replacement
  state invariants against the committed expected outputs;
- a third workflow can use the same cases as a DuckDB/Spark conformance check.

## Exclusions

Gate 0 does not claim the first, only, complete, production-ready, or statistically representative
benchmark. It does not publish a leaderboard, a performance result, source rows, or a complete
archive survey.
