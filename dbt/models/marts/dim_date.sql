-- Date spine covering the archive window with headroom for daily increments.
-- Spine generation is the one engine-specific piece (Snowflake generator vs DuckDB
-- generate_series); every derived column goes through portable functions/macros.
{% if target.type == 'duckdb' %}
with spine as (
    select cast(unnest(generate_series(date '2021-12-01', date '2028-12-31', interval 1 day)) as date) as d
)
{% else %}
with spine as (
    select dateadd(day, seq4(), '2021-12-01'::date) as d
    from table(generator(rowcount => 2588))  -- through 2028-12-31
)
{% endif %}
select
    {{ date_key_int('d') }}              as date_key,
    d                                    as date_day,
    year(d)                              as year,
    quarter(d)                           as quarter,
    month(d)                             as month,
    monthname(d)                         as month_name,
    day(d)                               as day_of_month,
    {{ iso_dow('d') }}                   as day_of_week_iso,
    dayname(d)                           as day_name,
    case when {{ iso_dow('d') }} >= 6 then true else false end as is_weekend
from spine
