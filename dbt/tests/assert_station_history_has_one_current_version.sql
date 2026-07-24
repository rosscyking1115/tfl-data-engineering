-- Fail a business key with no current row, multiple current rows, or a closed
-- version whose exclusive end does not advance beyond its start.

with invalid_current_rows as (

    select bikepoint_id
    from {{ ref('dim_station_history') }}
    group by bikepoint_id
    having sum(case when is_current then 1 else 0 end) <> 1

), invalid_windows as (

    select bikepoint_id
    from {{ ref('dim_station_history') }}
    where valid_to is not null
      and valid_to <= valid_from

)

select bikepoint_id from invalid_current_rows
union
select bikepoint_id from invalid_windows
