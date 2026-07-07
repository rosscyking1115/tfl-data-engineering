-- Date spine covering the archive window with headroom for daily increments.
with spine as (
    select dateadd(day, seq4(), '2021-12-01'::date) as d
    from table(generator(rowcount => 2588))  -- through 2028-12-31
)
select
    to_number(to_char(d, 'YYYYMMDD'))   as date_key,
    d                                    as date_day,
    year(d)                              as year,
    quarter(d)                           as quarter,
    month(d)                             as month,
    monthname(d)                         as month_name,
    day(d)                               as day_of_month,
    dayofweekiso(d)                      as day_of_week_iso,
    dayname(d)                           as day_name,
    case when dayofweekiso(d) >= 6 then true else false end as is_weekend
from spine
