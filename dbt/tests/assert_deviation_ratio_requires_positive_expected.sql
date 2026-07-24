-- Missing or zero expected demand must never become a meaningful uplift ratio.
select *
from {{ ref('demand_deviation') }}
where (expected_departures is null or expected_departures <= 0)
  and deviation_ratio is not null
