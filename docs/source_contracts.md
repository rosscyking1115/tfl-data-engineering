# Source contracts

What each upstream source provides, what this pipeline depends on, and how a breaking change
surfaces. The "we depend on" line is the tripwire: if any of those fields drift, a gate fails
loudly (never silent mis-parsing). Verified against primary docs + observed payloads.

## 1 · Santander journey extracts (the analytical backbone)

| | |
|---|---|
| Endpoint | `https://s3-eu-west-1.amazonaws.com/cycling.data.tfl.gov.uk/` (public S3; `?list-type=2&prefix=usage-stats/`). The vanity domain serves an HTML browser, not XML. |
| Auth / limits | None (open data). Bulk HTTP GET. |
| Cadence | New extract every ~2 weeks, covering a start-date window, published with a **~1–2 month lag**. Filename: `NNNJourneyDataExtractDDMmmYYYY-DDMmmYYYY.csv`. |
| Schema (nextgen era) | `Number, Start date, End date, Bike number, Bike model, Total duration (ms), Start station number, Start station, End station number, End station` |
| Known quirks | Cross-year schema drift (5 ordered-header variants verified across the 148 retained files — see ADR-0002); boundary spill/re-coverage can occur; rides can end after the filename window. The 2022–May 2026 backfill found **zero** overlapping rental IDs. Duplicate object replay remains a constructed guard pending genuine older-source evidence, not an observed incident in that window. |
| We depend on | The 10 nextgen columns above by **name** (`REQUIRED_COLUMNS` in [journey_increment.py](../ingestion/journey_increment.py)); the filename date pattern for the watermark. |
| Breakage surfaces as | The **schema gate** (`SystemExit: schema gate`) or the filename regex matching nothing (increment reports up-to-date while the coverage/freshness layer flags stalling journeys). |

## 2 · TfL Unified API — Line Status (the disruption signal)

| | |
|---|---|
| Endpoint | `GET https://api.tfl.gov.uk/Line/Mode/tube,dlr,overground,elizabeth-line,tram/Status` |
| Auth / limits | Anonymous works (throttled ~50 req/min); `app_key` raises to 500 req/min. One call/day used. |
| Cadence | Live state only — **no historical archive**. History exists only because we snapshot daily (permanent-if-collected; ADR-0009 two-horizon). |
| Shape | Per line: `id, name, modeName, lineStatuses[] {statusSeverity, statusSeverityDescription, reason}`. `statusSeverity == 10` = Good Service; lower = worse. |
| We depend on | `id, name, modeName`, `lineStatuses[].statusSeverity/statusSeverityDescription/reason`. |
| Breakage surfaces as | The row-count **quality gate** (<15 lines) or dbt schema tests on the snapshot staging model. |

## 3 · TfL Unified API — BikePoint (live dock state)

| | |
|---|---|
| Endpoint | `GET https://api.tfl.gov.uk/BikePoint` |
| Auth / limits | As above. One call/day. |
| Shape | ~800 places with `id, commonName, lat, lon` + `additionalProperties` (`NbBikes, NbEmptyDocks, NbDocks, NbEBikes`). |
| Known quirks | Property values are strings and can be **missing or corrupt** (a corrupt `NbDocks` caused the 2026-07-11..13 outage — now NA-safe). `commonName` doesn't always match journey-file station names verbatim (93% match after whitespace collapsing). |
| We depend on | `id, commonName, lat, lon` + the four count properties, parsed leniently to `None` (no data ≠ zero). |
| Breakage surfaces as | Quality gate (<700 docks) or NaN-rate spikes visible on the health page. |

## 4 · Open-Meteo archive (confounder control)

| | |
|---|---|
| Endpoint | `GET https://archive-api.open-meteo.com/v1/archive` (daily variables, `timezone=Europe/London`) |
| Auth / limits | None for non-commercial use. Recent days lag ~2–5 days in the archive. |
| We depend on | `temperature_2m_mean, temperature_2m_max, precipitation_sum, rain_sum, wind_speed_10m_max, weather_code` per calendar day. |
| Breakage surfaces as | HTTP failure (retried w/ backoff, then loud) or missing-day joins falling to the `false` weather bucket (bounded by the sensitivity battery, ADR-0009). |

## Attribution

Journey, line-status and BikePoint data: **Powered by TfL Open Data**. Contains OS data
© Crown copyright and database rights 2016; Geomni UK Map data © and database rights 2019.
Weather: [Open-Meteo](https://open-meteo.com/) (CC-BY 4.0).
