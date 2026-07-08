{{ config(materialized='external', location='app/gold_export/expected_demand.parquet') }}

-- Weather-adjusted baseline: expected daily departures per station, conditioned on
-- day-of-week and weather bucket (wet? cold?). Median is robust to the long tail.
-- This is what "normal" looks like, so a disruption's effect can be isolated from
-- ordinary weekday/weather variation (see the 2024-01-08 cold-strike counterexample).

with flows as (
    select
        f.date_key,
        f.station_key,
        s.station_name,
        f.departures,
        cast(strptime(cast(f.date_key as varchar), '%Y%m%d') as date) as date_day
    from {{ source('gold_export', 'station_daily_flows') }} f
    join {{ source('gold_export', 'dim_station') }} s on f.station_key = s.station_key
),

enriched as (
    select
        flows.station_key,
        flows.station_name,
        flows.departures,
        isodow(flows.date_day) as dow,
        coalesce(w.is_wet, false)  as is_wet,
        coalesce(w.is_cold, false) as is_cold
    from flows
    left join {{ source('gold_export', 'weather_daily') }} w on flows.date_key = w.date_key
)

select
    station_key,
    any_value(station_name)          as station_name,
    dow,
    is_wet,
    is_cold,
    median(departures)               as expected_departures,
    count(*)                         as n_observations
from enriched
group by station_key, dow, is_wet, is_cold
