-- The API-derived disruption log is forward-collected only.
select *
from {{ ref('disruption_events') }}
where start_date < cast('2026-07-08' as date)
