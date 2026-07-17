# Power BI on the gold layer (PL-300 tie-in)

> [!NOTE]
> **Superseded by [`powerbi/`](../../powerbi/).** This page describes the original **Snowflake**
> connection, which is a documented past phase (the trial expires). The current, durable build
> reads committed Parquet instead. See [`powerbi/README.md`](../../powerbi/README.md) for the
> model-as-code (DAX + Power Query M + TMDL) and build guide. This page is kept for history.

The dashboard connects directly to `TFL.GOLD`; dbt has already shaped the tables.

## Connect

Power BI Desktop → Get Data → **Snowflake**:

| field | value |
|---|---|
| Server | `<SNOWFLAKE_ACCOUNT>.snowflakecomputing.com` (account id is in `.env`) |
| Warehouse | `TFL_WH` |
| Database → Schema | `TFL` → `GOLD` |
| Auth | Snowflake username/password (same as `.env`) |

## Which tables, which storage mode

| table | rows | mode | use |
|---|---:|---|---|
| `DAILY_JOURNEY_STATS` | ~1.6k | Import | headline trends, weekday/weekend, e-bike share |
| `STATION_DAILY_FLOWS` | ~1.4M | Import | station map (lat/lon via `DIM_STATION`), net inflow |
| `DIM_STATION` | 856 | Import | names + both era codes |
| `DIM_DATE` | 2.6k | Import | date slicers |
| `BIKEPOINT_DAILY_SNAPSHOT` | 798/day | Import | live dock occupancy tile |
| `LINE_STATUS_DAILY` | ~20/day | Import | disruption tile |
| `FACT_JOURNEY` | 41M | **DirectQuery only if needed** | drill-to-detail page; keep off the default canvas so the XS warehouse isn't hammered by slicer spam |

Model relationships: `date_key` → `DIM_DATE`, `station_key` → `DIM_STATION`
(single-direction filters).

## Suggested pages

1. **Usage trends** — journeys/day line (2022→now, the Sep-2022 era switch is visible),
   weekday-vs-weekend split, e-bike share growth.
2. **Station flows** — map sized by departures, tooltip net inflow; top-10 stations bar.
3. **Today's network** — dock occupancy histogram + line-status table from the two
   snapshot tables (fed by the Airflow daily DAG).

## Cost note

Import mode = one warehouse spin per refresh; scheduled refresh once daily after the
07:00 dbt run keeps Power BI's contribution to credit burn at ~a cent a day.
