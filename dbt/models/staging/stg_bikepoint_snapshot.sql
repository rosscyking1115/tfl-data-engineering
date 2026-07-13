-- Normalizes the bikepoint snapshot across the two source shapes: the Snowflake-era
-- loader table (has installed/locked, DATE snapshot_date) and the durable committed
-- Parquet (no installed/locked, VARCHAR snapshot_date). Downstream marts see one shape.

{% if target.type == 'duckdb' %}

select
    cast(snapshot_date as date)   as snapshot_date,
    bikepoint_id,
    common_name,
    lat,
    lon,
    cast(null as boolean)         as installed,
    cast(null as boolean)         as locked,
    n_docks,
    n_bikes,
    n_empty_docks,
    n_ebikes,
    pulled_at
from {{ source('silver', 'BIKEPOINT_SNAPSHOT') }}

{% else %}

select
    snapshot_date,
    bikepoint_id,
    common_name,
    lat,
    lon,
    installed,
    locked,
    n_docks,
    n_bikes,
    n_empty_docks,
    n_ebikes,
    pulled_at
from {{ source('silver', 'BIKEPOINT_SNAPSHOT') }}

{% endif %}
