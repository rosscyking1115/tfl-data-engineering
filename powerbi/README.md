# Power BI — code-first dashboard on the durable Parquet

A Power BI report over the same gold layer as the Streamlit app, built **model-first**: the
semantic model and every measure live here as code, so the report is reproducible and
version-controlled rather than a black-box `.pbix`. It reads the **committed Parquet**
(`app/gold_export/`) directly — no Snowflake, so it survives the trial and needs no credentials.

## What's in this folder

| File | What it is |
|---|---|
| [`measures.dax`](measures.dax) | Every DAX measure, paste-ready. Cross-checked against DuckDB — reference values are in the comments. |
| [`queries.pq`](queries.pq) | Power Query (M) source per table — reads each Parquet via one `GoldExportFolder` parameter. |
| [`model.tmdl`](model.tmdl) | The star schema as TMDL (tables, partitions, relationships) — model-as-code. |

> [!NOTE]
> The DAX and M here are verified correct against the real data. The TMDL is hand-authored and
> **not opened in Power BI Desktop from this repo** (Desktop is a Windows GUI that can't run in the
> build environment). The **guaranteed** path is the manual build below; the TMDL is provided as a
> readable spec (and for Tabular Editor users). No claim is made that a one-click project opens.

## Build it (Power BI Desktop — the reliable path)

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
   card of **Disruption Demand Ratio** shows **≈ 1.42** and **Forecast Improvement %** ≈ **33%** —
   that's your "model loaded correctly" check.
6. Build the pages below, then *Publish* (or screenshot for the repo).

*Advanced:* Tabular Editor users can work from [`model.tmdl`](model.tmdl) instead of steps 3–5.

## Suggested pages (mirror the app)

1. **Usage trends** — cards: *Total Journeys*, *E-bike Share %*, *Avg Duration (min)*; a
   journeys-per-day line by `dim_date[date_day]` (the Sept-2022 era switch is visible); a
   weekday-vs-weekend bar (`dim_date[is_weekend]`).
2. **Disruption impact** (flagship) — cards: *Normal Demand Ratio* (≈1.00) vs *Disruption Demand
   Ratio* (≈1.42) and *Disruption Uplift %*; a bar of `deviation_ratio` by disruption date with a
   reference line at 1.0.
3. **Today's network** — a table of the latest not-good-service lines
   (`live_line_status`, filtered to *Latest Snapshot*, showing `line_name`, `status_description`,
   `reason`); cards *Docks Empty Now* / *Docks Full Now*; a histogram of `fill_rate`. A map is
   available here too — `live_bikepoint` has `lat`/`lon` (the journey tables don't).
4. *(Optional)* **Demand forecast** — *Forecast MAE (ML)* vs *Median Baseline MAE* and
   *Forecast Improvement %*; predicted-vs-actual over time from `demand_deviation_ml`.

<!-- Add a screenshot once built:
![Power BI dashboard](../docs/img/powerbi.png)
-->

## "Can AI build this for me?"

- **Fabric / Power BI Copilot** — Microsoft's built-in AI *can* generate pages, measures and
  narratives from this model, but it needs a **paid Fabric capacity (F2+)** or a Copilot license.
  Out of scope here (this project stays free).
- **Power BI MCP** (e.g. the `powerbi-modeling` tooling) — an AI↔Power BI bridge that connects to
  an **already-open** model in Desktop via the local engine to read structure and author measures.
  Works locally and free-ish, but it edits an open model rather than building one from scratch.
- **This folder is the free, portable middle ground:** the model and measures are generated as
  code; you assemble the visuals in Desktop (the hands-on part).

## Why Parquet, not Snowflake

The earlier [../docs/phase3/powerbi_guide.md](../docs/phase3/powerbi_guide.md) connected to
Snowflake `TFL.GOLD`. That warehouse is a documented past phase and its trial expires — so this
build targets the committed Parquet instead, keeping the dashboard runnable indefinitely with the
rest of the durable workflow.
