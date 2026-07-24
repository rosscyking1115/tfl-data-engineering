-- ADR-0009 historical treatment remains the cited seed, not the live event log.
select *
from {{ ref('disruption_dates') }}
where source_url is null or trim(source_url) = ''
