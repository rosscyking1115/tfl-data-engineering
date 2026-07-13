-- "No data ≠ zero" guard (rigor-pass Area 4, a named falsifier in ADR-0009): every calendar
-- day inside the journey archive window must have a daily_journey_stats row. A missing day
-- means the archive has a hole that downstream must treat as MISSING, never as zero demand.
-- WARN severity: a publisher gap shouldn't hard-fail builds, but it must be loudly visible.

{{ config(severity='warn') }}

with bounds as (
    select min(date_day) as lo, max(date_day) as hi
    from {{ ref('daily_journey_stats') }}
),

expected as (
    select cast(unnest(generate_series(lo, hi, interval 1 day)) as date) as d
    from bounds
),

actual as (
    select distinct cast(date_day as date) as d from {{ ref('daily_journey_stats') }}
)

select e.d as missing_journey_date
from expected e
left join actual a using (d)
where a.d is null
