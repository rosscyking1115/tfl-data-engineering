{{ config(materialized='external', location='app/gold_export/demand_deviation.parquet') }}

-- Per station per day: actual vs weather-adjusted expected departures, flagged for
-- known transport-disruption dates. This is the headline analytical table — it turns
-- "strikes boost cycling" into a measured, per-station, weather-controlled number.

with actual as (
    select
        f.date_key,
        cast(strptime(cast(f.date_key as varchar), '%Y%m%d') as date) as date_day,
        f.station_key,
        s.station_name,
        f.departures,
        isodow(cast(strptime(cast(f.date_key as varchar), '%Y%m%d') as date)) as dow,
        coalesce(w.is_wet, false)  as is_wet,
        coalesce(w.is_cold, false) as is_cold
    from {{ source('gold_export', 'station_daily_flows') }} f
    join {{ source('gold_export', 'dim_station') }} s on f.station_key = s.station_key
    left join {{ source('gold_export', 'weather_daily') }} w on f.date_key = w.date_key
)

select
    a.date_key,
    a.date_day,
    a.station_key,
    a.station_name,
    a.departures,
    b.expected_departures,
    a.departures - b.expected_departures                              as deviation,
    round(a.departures / nullif(b.expected_departures, 0), 3)         as deviation_ratio,
    (dd.date is not null)                                             as is_disruption,
    dd.severity                                                       as disruption_severity
from actual a
left join {{ ref('expected_demand') }} b
    on a.station_key = b.station_key
   and a.dow = b.dow
   and a.is_wet = b.is_wet
   and a.is_cold = b.is_cold
left join {{ ref('disruption_dates') }} dd
    on a.date_day = cast(dd.date as date)
