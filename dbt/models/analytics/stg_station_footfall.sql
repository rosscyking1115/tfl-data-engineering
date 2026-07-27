-- Daily rail entry/exit taps per station, typed and whitespace-normalised.
--
-- Grain: date_key x rail_station. This is a CONTEXT series, not evidence about cycling:
-- taps are gate events on the rail network, counted for a different population from the
-- cycle-hire journeys. It is deliberately NOT joined to dim_station anywhere in this
-- project (see docs/source_contracts.md and ADR-0013).

select
    cast(date_key as integer)                             as date_key,
    cast(strptime(cast(date_key as varchar), '%Y%m%d') as date) as travel_date,
    day_of_week,
    {{ dbt_utils.generate_surrogate_key(['rail_station']) }} as rail_station_key,
    trim(regexp_replace(rail_station, '\s+', ' ', 'g'))    as rail_station,
    cast(entry_taps as bigint)                            as entry_taps,
    cast(exit_taps as bigint)                             as exit_taps,
    cast(entry_taps as bigint) + cast(exit_taps as bigint) as total_taps,
    pulled_at
from {{ source('gold_export', 'station_footfall') }}
