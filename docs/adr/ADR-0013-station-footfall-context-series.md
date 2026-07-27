# ADR-0013 — Station footfall as a context series, not evidence

## Context

The workflow's most awkward documented limitation is that the journey extracts are
published in bulk with a **~1–2 month lag** (ADR-0006), which forces the honest split
between historical quantification and live monitoring. The live layer has, until now,
only had same-day API snapshots with no measured series behind them.

TfL publishes daily per-station entry and exit tap counts to
`crowding.data.tfl.gov.uk` as `StationFootfall_*.csv`. Verified 2026-07-27: the current
file was last modified 2026-07-22 and carried data through 2026-07-18 — a **four-day
lag**, against 1–2 months for journeys. Seven non-overlapping files cover 2019-01-01
onward, 1,166,182 rows over 439 stations, 5.26 MB as zstd Parquet.

A 2026-07-27 product scan found no product route here and confirmed that Tube-relevant
published history is under 2GB, so nothing about this justifies changing the DuckDB /
Parquet / GitHub Actions runtime. This is a data upgrade, not a feature.

## Decision

Ingest station footfall as a **context series for the live layer**, and constrain what it
is allowed to mean.

Taps are gate events on the **rail** network. They are not journeys, they are not a
cycle-hire measure, and they are not the same population as the cycle data. Therefore:

- The station column is named `rail_station`, not `station_name`, so an accidental join
  to `dim_station` is visibly wrong rather than quietly plausible.
- Nothing in the project joins footfall to the cycle star schema, and the ADR-0009
  certified evidence, its grain, comparator and permitted observed-association wording
  are untouched.
- The series does not feed the disruption estimate, the forecast, or any claim about
  what the repo proves.

Ingestion is `ingestion/station_footfall.py`: incremental by default (the current rolling
file only), `--backfill` for the full set, upserting on `(date_key, rail_station)`. Three
verified source quirks are handled by name rather than position, matching ADR-0002's rule:

- Header case drifts — `DayOFWeek` for 2019–2022, `DayOfWeek` from 2023.
- 2019–2023 files carry a UTF-8 BOM; 2024 onward do not.
- The two rolling files have a literal space before `.csv` in their key.

The published files also **overlap**: `StationFootfall_2024_2025` spans 20240101–20251227
and fully contains `StationFootfall_2024` plus half of the current file. Concatenating
everything would double-count two whole years. The backfill set is therefore explicitly
non-overlapping, and the upsert key makes a mistake idempotent rather than additive.
Where the files do overlap they agree exactly — 156,995 rows compared across 2024, zero
disagreements — so dropping the redundant file loses nothing.

## Consequences

The live layer gains a measured daily series that is days rather than months behind, which
narrows the gap ADR-0006 documents. It does **not** remove that limitation: journey data
still lags, and footfall cannot stand in for it, because it measures a different thing.

The claim that footfall is the fresher series is itself testable, so it is tested.
`assert_footfall_leads_journey_coverage` fails if footfall coverage stops leading journey
coverage — either the feed stalled and the framing is no longer true, or journeys caught
up and the series is redundant. `dbt source freshness` covers the new source with
deliberately loose thresholds (warn 10 days, error 21), because one observed re-publish is
not enough to assert a weekly cadence.

Cost is one 10 MB weekly fetch and 5.26 MB of committed Parquet — inside the durable-and-free
constraint, with no change to the runtime.
