-- Normalizes the line-status snapshot across the two source shapes: the Snowflake-era
-- loader table (disruption_reason, DATE snapshot_date) and the durable committed Parquet
-- (reason, VARCHAR snapshot_date). Downstream marts see one shape.

{% if target.type == 'duckdb' %}

select
    cast(snapshot_date as date)   as snapshot_date,
    line_id,
    line_name,
    mode,
    status_severity,
    status_description,
    reason                        as disruption_reason,
    pulled_at
from {{ source('silver', 'LINE_STATUS_SNAPSHOT') }}

{% else %}

select
    snapshot_date,
    line_id,
    line_name,
    mode,
    status_severity,
    status_description,
    disruption_reason,
    pulled_at
from {{ source('silver', 'LINE_STATUS_SNAPSHOT') }}

{% endif %}
