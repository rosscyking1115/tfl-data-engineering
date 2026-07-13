-- Daily dock occupancy at snapshot_date x bikepoint grain. station_key links a
-- dock to dim_station by name where the names line up (nullable — BikePoint
-- common names don't always match journey-file station names verbatim).

with bikepoint as (
    select * from {{ ref('stg_bikepoint_snapshot') }}
),

stations as (
    select station_key, station_name from {{ ref('dim_station') }}
)

select
    {{ date_key_int('b.snapshot_date') }}                    as date_key,
    b.snapshot_date,
    b.bikepoint_id,
    {{ collapse_ws('b.common_name') }}                       as common_name,
    s.station_key,
    b.lat,
    b.lon,
    b.installed,
    b.locked,
    b.n_docks,
    b.n_bikes,
    b.n_empty_docks,
    b.n_ebikes,
    case when b.n_docks > 0
         then round(b.n_bikes / b.n_docks, 3)
    end                                                      as occupancy_rate,
    b.pulled_at
from bikepoint b
left join stations s
    on {{ collapse_ws('b.common_name') }} = s.station_name
