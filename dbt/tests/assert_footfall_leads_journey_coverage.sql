-- The whole reason station footfall was added (ADR-0013) is that it closes the journey
-- extracts' 1-2 month publishing lag. That is a claim, so it gets a tripwire.
--
-- Fail if footfall coverage stops leading journey coverage. Either the footfall feed has
-- stalled (in which case the "fresher context series" framing is no longer true and the
-- README should stop saying so), or journeys have caught up and footfall is redundant.
-- Both are things a reader deserves to know rather than us asserting the benefit forever.

with footfall as (
    select max(travel_date) as max_date from {{ ref('stg_station_footfall') }}
),

journeys as (
    select max(cast(strptime(cast(date_key as varchar), '%Y%m%d') as date)) as max_date
    from {{ source('gold_export', 'station_daily_flows') }}
)

select
    footfall.max_date as footfall_max_date,
    journeys.max_date as journey_max_date
from footfall
cross join journeys
where footfall.max_date <= journeys.max_date
