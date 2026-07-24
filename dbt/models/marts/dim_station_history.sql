-- Station-attribute SCD2 history at BikePoint ID x attribute-version grain.
-- This is deliberately separate from the journey-era dim_station: BikePoint
-- names do not always conform to journey-file names, so a forced bridge would
-- overstate identity certainty. Occupancy measures are facts, not attributes.

with normalized as (

    select
        cast(snapshot_date as date) as snapshot_date,
        bikepoint_id,
        coalesce(common_name, 'unknown') as common_name,
        lat,
        lon,
        n_docks,
        lower(coalesce(cast(installed as {{ dbt.type_string() }}), 'unknown')) as installed_state,
        lower(coalesce(cast(locked as {{ dbt.type_string() }}), 'unknown')) as locked_state
    from {{ ref('stg_bikepoint_snapshot') }}

), signatures as (

    select
        *,
        {{ dbt_utils.generate_surrogate_key([
            'common_name',
            'lat',
            'lon',
            'n_docks',
            'installed_state',
            'locked_state',
        ]) }} as attribute_signature
    from normalized

), marked as (

    select
        *,
        case
            when lag(attribute_signature) over (
                partition by bikepoint_id
                order by snapshot_date
            ) is null
            or attribute_signature <> lag(attribute_signature) over (
                partition by bikepoint_id
                order by snapshot_date
            ) then 1
            else 0
        end as starts_new_version
    from signatures

), numbered as (

    select
        *,
        sum(starts_new_version) over (
            partition by bikepoint_id
            order by snapshot_date
            rows between unbounded preceding and current row
        ) as version_number
    from marked

), version_starts as (

    select
        bikepoint_id,
        common_name,
        lat,
        lon,
        n_docks,
        installed_state,
        locked_state,
        version_number,
        min(snapshot_date) as valid_from
    from numbered
    group by 1, 2, 3, 4, 5, 6, 7, 8

), version_windows as (

    select
        *,
        lead(valid_from) over (
            partition by bikepoint_id
            order by valid_from
        ) as valid_to
    from version_starts

)

select
    bikepoint_id,
    common_name,
    lat,
    lon,
    n_docks,
    installed_state,
    locked_state,
    valid_from,
    valid_to,
    valid_to is null as is_current
from version_windows
