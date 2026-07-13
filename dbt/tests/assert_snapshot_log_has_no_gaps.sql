-- Temporal-coverage guard for the forward-accumulated disruption log (rigor-pass Area 4):
-- every calendar day between the first and latest snapshot must be present. A missing day
-- is a PERMANENT hole (the API has no history), so surface it — but at WARN severity:
-- one missed cron day shouldn't hard-fail every future build; it should be loudly visible.

{{ config(severity='warn') }}

with bounds as (
    select min(snapshot_date) as lo, max(snapshot_date) as hi
    from {{ ref('stg_line_status_snapshot') }}
),

expected as (
    select cast(unnest(generate_series(lo, hi, interval 1 day)) as date) as d
    from bounds
),

actual as (
    select distinct snapshot_date as d from {{ ref('stg_line_status_snapshot') }}
)

select e.d as missing_snapshot_date
from expected e
left join actual a using (d)
where a.d is null
