# ADR-0012 — Station attribute history and operational alert coverage

## Context

The project has a journey-era `dim_station`, while daily BikePoint snapshots
carry a different, forward-collected source of station attributes. The prior
portfolio polish also left a deliberate failure demo beside the real local
operational DAGs.

## Decision

`dim_station_history` is a separate SCD2 mart at `bikepoint_id ×
attribute-version` grain. It tracks name, coordinates, dock capacity and
installed/locked state with `valid_from`, exclusive `valid_to`, and
`is_current`. It does not track daily occupancy measures, and it does not force
a name-based bridge into the journey `dim_station` because that mapping is not
universally conforming.

The synthetic `failure_alert_demo` is retired. The real local daily-ingest,
dbt-gate and monthly archive-drift DAGs share the failure callback; its critical
task-log event is the local evidence, while the webhook remains opt-in and is
not exercised by this project.

## Consequences

This adds an explicit, testable SCD2 interview story without changing the
ADR-0009 analytical grain, certified evidence, permitted observed-association
wording, source snapshots, or GitHub Actions runtime.
