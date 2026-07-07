# Phase 2 findings — dbt star schema (2026-07-07)

`dbt build`: **28/28 green on first run**, ~50 s wall clock on the XS warehouse.

| model | rows | build time |
|---|---:|---:|
| stg_journeys (view) | — | 0.6 s |
| dim_date | 2,588 | 1.7 s |
| dim_station | 856 | 24.4 s |
| fact_journey | 41,376,181 | 20.7 s |

## The dim_station design (the interesting part)

The two eras use disjoint station-ID spaces (classic integer ids vs nextgen
zero-padded terminal codes), and one 2022 file has no end-station id column at all.
Cleaned station **name** is the only key present everywhere, so it conforms the
dimension; the era-specific codes are kept as attributes (`classic_station_id`,
`nextgen_station_code`). Result: 856 stations, and the `not_null` test on
`fact_journey.end_station_key` **passes** — the name join repaired all 312,144
id-less rows.

## Test contract (models/*/schema.yml)

- keys: `journey_key`, `station_key`, `date_key` unique + not_null; (`era`,
  `rental_id`) unique combination
- ranges: `duration_s >= 1`; `start_date_key` within 20211201–20281231
- relationships: fact → dim_station (both ends), fact → dim_date
- era accepted_values at staging

## Sanity queries through the star

Top station all-time: Hyde Park Corner (287k departures) — matches TfL's own
published rankings. Weekend rides run longer than weekday in both eras (24.6 vs
19.2 min classic; 30.9 vs 21.7 nextgen) — the expected leisure-vs-commute signal.

## Cost

Phase 2 build + sanity queries: ~0.11 credits (~$0.33). Running trial total ~0.35
credits of $400.
