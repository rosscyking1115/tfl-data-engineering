-- Reporting rollup for Power BI: one row per day. Import-friendly (~1.6k rows)
-- so the dashboard never has to pull the 41M-row fact over the wire.
select
    f.start_date_key                       as date_key,
    d.date_day,
    d.year,
    d.month_name,
    d.day_name,
    d.is_weekend,
    count(*)                               as journeys,
    round(avg(f.duration_s) / 60, 2)       as avg_duration_min,
    round(median(f.duration_s) / 60, 2)    as median_duration_min,
    count(distinct f.bike_id)              as distinct_bikes,
    sum(case when f.bike_model = 'PBSC_EBIKE' then 1 else 0 end) as ebike_journeys
from {{ ref('fact_journey') }} f
join {{ ref('dim_date') }} d on f.start_date_key = d.date_key
group by 1, 2, 3, 4, 5, 6
