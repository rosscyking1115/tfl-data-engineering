-- One row per station, unified across the two ID regimes by cleaned name.
-- classic era used integer ids (e.g. 197); nextgen uses zero-padded terminal
-- codes in new ranges (e.g. 001211) — same physical docks, different id space.
-- Name is the only key present in every era AND in the 312k rows whose
-- end-station id column didn't exist, so name is the conforming key and the
-- era-specific codes become attributes.

with station_events as (

    select
        start_station_name as station_name,
        start_station_code as station_code,
        era,
        start_ts           as seen_ts
    from {{ ref('stg_journeys') }}
    where start_station_name is not null and start_station_name <> ''

    union all

    select
        end_station_name,
        end_station_code,
        era,
        end_ts
    from {{ ref('stg_journeys') }}
    where end_station_name is not null and end_station_name <> ''

)

select
    {{ dbt_utils.generate_surrogate_key(['station_name']) }} as station_key,
    station_name,
    max(case when era = 'classic' then station_code end)     as classic_station_id,
    max(case when era = 'nextgen' then station_code end)     as nextgen_station_code,
    min(seen_ts)                                             as first_seen_ts,
    max(seen_ts)                                             as last_seen_ts,
    count(*)                                                 as dock_events
from station_events
group by station_name
