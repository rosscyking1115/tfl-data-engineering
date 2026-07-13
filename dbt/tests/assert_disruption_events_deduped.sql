-- The de-dup invariant for disruption_events: no two events for the same line may be
-- temporally adjacent or overlapping — adjacent/overlapping days must have collapsed
-- into ONE event. Any row returned here is a de-dup failure.

select
    a.line_id,
    a.start_date as a_start,
    a.end_date   as a_end,
    b.start_date as b_start
from {{ ref('disruption_events') }} a
join {{ ref('disruption_events') }} b
  on a.line_id = b.line_id
 and a.start_date < b.start_date
 and b.start_date <= a.end_date + 1
