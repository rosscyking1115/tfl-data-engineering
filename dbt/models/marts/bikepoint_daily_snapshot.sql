-- Daily dock occupancy at snapshot_date x bikepoint grain. station_key links a
-- dock to dim_station by name where the names line up (nullable — BikePoint
-- common names don't always match journey-file station names verbatim).

with bikepoint as (
    select * from {{ source('silver', 'BIKEPOINT_SNAPSHOT') }}
),

stations as (
    select station_key, station_name from {{ ref('dim_station') }}
)

select
    to_number(to_char(b.snapshot_date, 'YYYYMMDD'))         as date_key,
    b.snapshot_date,
    b.bikepoint_id,
    regexp_replace(trim(b.common_name), '\\s+', ' ')        as common_name,
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
    on regexp_replace(trim(b.common_name), '\\s+', ' ') = s.station_name
