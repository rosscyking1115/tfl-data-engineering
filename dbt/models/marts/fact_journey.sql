-- Journey grain: one row per hire. Station foreign keys resolve by cleaned
-- name (see dim_station) — this also repairs the 312k rows that lost their
-- end-station id to the 2022 header variant.

with journeys as (
    select * from {{ ref('stg_journeys') }}
),

stations as (
    select station_key, station_name from {{ ref('dim_station') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['j.era', 'j.rental_id']) }} as journey_key,
    j.era,
    j.rental_id,
    {{ date_key_int('j.start_date') }}           as start_date_key,
    s_start.station_key                          as start_station_key,
    s_end.station_key                            as end_station_key,
    j.start_ts,
    j.end_ts,
    j.duration_s,
    j.bike_id,
    j.bike_model
from journeys j
left join stations s_start on j.start_station_name = s_start.station_name
left join stations s_end   on j.end_station_name   = s_end.station_name
