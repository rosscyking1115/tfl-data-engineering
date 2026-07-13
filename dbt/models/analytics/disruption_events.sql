{{ config(materialized='external', location='app/gold_export/disruption_events.parquet', tags=['analytics']) }}

-- Forward-accumulated disruption EVENTS, derived from the daily line-status snapshot log
-- (ingestion/live_snapshot.py, collected since 2026-07-08). Complements the curated,
-- citation-backed strike seed (disruption_dates.csv): the seed gives deep strike history;
-- this grows a complete event log for ALL disruption types from the day collection began.
--
-- Operational definition (rigor-pass Area 2; see ADR-0009):
--  * A line-day QUALIFIES when any of its statuses has status_severity < 10
--    (TfL: 10 = Good Service; lower = worse). worst = MIN(severity) that day.
--  * Consecutive qualifying days for the same line collapse into ONE event
--    (gaps-and-islands), so a multi-day incident seen in several snapshots is not
--    double-counted. Boundaries are at day resolution — the snapshot cadence.

with line_days as (

    select
        snapshot_date,
        line_id,
        any_value(line_name)                             as line_name,
        any_value(mode)                                  as mode,
        min(status_severity)                             as worst_severity,
        arg_min(status_description, status_severity)     as worst_status,
        arg_min(disruption_reason, status_severity)      as sample_reason
    from {{ ref('stg_line_status_snapshot') }}
    where status_severity < 10
    group by snapshot_date, line_id

),

islands as (

    -- consecutive dates per line share the same (date - row_number) anchor
    select
        *,
        snapshot_date - cast(row_number() over (
            partition by line_id order by snapshot_date
        ) as integer)                                    as island_anchor
    from line_days

)

select
    line_id,
    any_value(line_name)                          as line_name,
    any_value(mode)                               as mode,
    min(snapshot_date)                            as start_date,
    max(snapshot_date)                            as end_date,
    count(*)                                      as days_observed,
    min(worst_severity)                           as worst_severity,
    arg_min(worst_status, worst_severity)         as worst_status,
    arg_min(sample_reason, worst_severity)        as sample_reason
from islands
group by line_id, island_anchor
