-- Daily line status at snapshot_date x line x status grain (a line can carry
-- multiple simultaneous statuses, e.g. part closure + minor delays).
select
    to_number(to_char(snapshot_date, 'YYYYMMDD')) as date_key,
    snapshot_date,
    line_id,
    line_name,
    mode,
    status_severity,
    status_description,
    disruption_reason,
    status_severity = 10                          as is_good_service,
    pulled_at
from {{ source('silver', 'LINE_STATUS_SNAPSHOT') }}
