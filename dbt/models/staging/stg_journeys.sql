-- Light cleanup only: trims/collapses station names so the two ID regimes can be
-- unified by name in dim_station. No filtering — grain identical to silver.
select
    era,
    rental_id,
    bike_id,
    bike_model,
    start_ts,
    end_ts,
    duration_s,
    start_station_code,
    regexp_replace(trim(start_station_name), '\\s+', ' ')  as start_station_name,
    end_station_code,
    regexp_replace(trim(end_station_name), '\\s+', ' ')    as end_station_name,
    to_date(start_ts)                                       as start_date,
    source_file
from {{ source('silver', 'JOURNEYS') }}
