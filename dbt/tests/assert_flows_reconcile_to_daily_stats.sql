-- Reconciliation inside dbt (rigor-pass Area 4): the station-level rollup and the daily
-- rollup are built independently from fact_journey, so their per-day departure totals must
-- agree EXACTLY. A mismatch means a broken join silently dropped or duplicated journeys —
-- the single most likely aggregation bug. ERROR severity: this must never ship.

with flows as (
    select date_key, sum(departures) as dep
    from {{ ref('station_daily_flows') }}
    group by 1
),

daily as (
    select date_key, sum(journeys) as journeys
    from {{ ref('daily_journey_stats') }}
    group by 1
)

select
    coalesce(f.date_key, d.date_key) as date_key,
    f.dep,
    d.journeys
from flows f
full outer join daily d using (date_key)
where coalesce(f.dep, -1) <> coalesce(d.journeys, -1)
  -- arrival-only spillover days are legitimate: rides that END after the last published
  -- start date give flows rows with 0 departures and (correctly) no daily_journey_stats
  -- row. Everything else must match exactly.
  and not (coalesce(f.dep, 0) = 0 and d.journeys is null)
