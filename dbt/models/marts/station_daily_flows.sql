-- Reporting rollup: departures and arrivals per station per day (~1.4M rows).
-- Powers station-flow maps without touching the raw fact.
with departures as (
    select start_date_key as date_key, start_station_key as station_key,
           count(*) as departures
    from {{ ref('fact_journey') }}
    group by 1, 2
),

arrivals as (
    select {{ date_key_int('cast(end_ts as date)') }} as date_key,
           end_station_key as station_key,
           count(*) as arrivals
    from {{ ref('fact_journey') }}
    group by 1, 2
)

select
    coalesce(d.date_key, a.date_key)       as date_key,
    coalesce(d.station_key, a.station_key) as station_key,
    s.station_name,
    coalesce(d.departures, 0)              as departures,
    coalesce(a.arrivals, 0)                as arrivals,
    coalesce(a.arrivals, 0) - coalesce(d.departures, 0) as net_inflow
from departures d
full outer join arrivals a
    on d.date_key = a.date_key and d.station_key = a.station_key
join {{ ref('dim_station') }} s
    on coalesce(d.station_key, a.station_key) = s.station_key
