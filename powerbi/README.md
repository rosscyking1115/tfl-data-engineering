# Power BI model over committed Parquet

This folder defines a Power BI report over the same gold layer as the Streamlit app. The semantic
model and measures are stored as code, so changes can be reviewed in Git instead of being hidden
inside a `.pbix` file. The report reads the **committed Parquet** in `app/gold_export/` and needs no
Snowflake credentials.

## What's in this folder

| File | What it is |
|---|---|
| [`measures.dax`](measures.dax) | Paste-ready DAX measures, cross-checked against DuckDB. Reference values are in the comments. |
| [`queries.pq`](queries.pq) | One Power Query (M) source per table, using a shared `GoldExportFolder` parameter. |
| [`model.tmdl`](model.tmdl) | The star schema as TMDL: tables, partitions and relationships. |

> [!NOTE]
> The DAX and M here are verified correct against the real data. The TMDL is hand-authored and
> **not opened in Power BI Desktop from this repository** because Desktop cannot run in the build
> environment. Use the manual steps below. The TMDL is a readable specification that can also be
> used with Tabular Editor; this repository does not claim a one-click project build.

## Build it in Power BI Desktop

1. **Clone the repo** locally so the Parquet files exist on disk.
2. **New report** → *Transform data* → *Manage Parameters* → **New**:
   `GoldExportFolder` · Text · current value = `<clone>\app\gold_export`
   (e.g. `C:\dev\portfolio\tfl-data-engineering\app\gold_export`).
3. For each block in [`queries.pq`](queries.pq): *New Source → Blank Query → Advanced Editor*,
   paste, and rename the query to the table name. *Close & Apply*.
4. **Model view** → create the relationships (all single-direction, dimension → fact):
   `station_daily_flows[date_key] → dim_date[date_key]`,
   `station_daily_flows[station_key] → dim_station[station_key]`,
   `daily_journey_stats[date_key] → dim_date[date_key]`,
   `demand_deviation[date_key] → dim_date[date_key]`, `[station_key] → dim_station[station_key]`,
   and the same two for `demand_deviation_ml`.
5. Paste each measure from [`measures.dax`](measures.dax) (*Modeling → New measure*). Confirm a
   card of **Disruption Demand Ratio** shows **≈ 1.42** and **Forecast Improvement %** ≈ **33%** to
   confirm that the model loaded correctly.
6. Build the pages below, then *Publish* (or screenshot for the repo).

*Advanced:* Tabular Editor users can work from [`model.tmdl`](model.tmdl) instead of steps 3–5.

## Suggested pages (mirror the app)

1. **Usage trends:** cards for *Total Journeys*, *E-bike Share %* and *Avg Duration (min)*; a
   journeys-per-day line by `dim_date[date_day]` (the Sept-2022 era switch is visible); a
   weekday-vs-weekend bar (`dim_date[is_weekend]`).
2. **Disruption impact:** cards for *Normal Demand Ratio* (≈1.00) versus *Disruption Demand
   Ratio* (≈1.42) and *Disruption Uplift %*; a bar of `deviation_ratio` by disruption date with a
   reference line at 1.0.
3. **Today's network:** a table of the latest not-good-service lines
   (`live_line_status`, filtered to *Latest Snapshot*, showing `line_name`, `status_description`,
   `reason`); cards *Docks Empty Now* / *Docks Full Now*; a histogram of `fill_rate`. A map is
   available here because `live_bikepoint` has `lat` and `lon` (the journey tables do not).
4. *(Optional)* **Demand forecast:** *Forecast MAE (ML)* versus *Median Baseline MAE* and
   *Forecast Improvement %*; predicted-vs-actual over time from `demand_deviation_ml`.

<!-- Add a screenshot once built:
![Power BI dashboard](../docs/img/powerbi.png)
-->

## AI-assisted options

- **Fabric / Power BI Copilot:** Microsoft's built-in AI can generate pages, measures and
  narratives from this model, but it needs a **paid Fabric capacity (F2+)** or a Copilot license.
  Out of scope here (this project stays free).
- **Power BI MCP** (for example, `powerbi-modeling`) connects an AI client to
  an **already-open** model in Desktop via the local engine to read structure and author measures.
  It works locally but edits an open model instead of building one from scratch.
- The files in this folder are the free option: the model and measures are code, while the visuals
  are assembled manually in Desktop.

## Why Parquet, not Snowflake

The earlier [../docs/phase3/powerbi_guide.md](../docs/phase3/powerbi_guide.md) connected to
Snowflake `TFL.GOLD`. That warehouse belongs to an earlier trial-based phase. The current build
uses committed Parquet so the report remains reproducible without the warehouse.
