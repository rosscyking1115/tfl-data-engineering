// TfL Cycle-Hire — Power Query (M) sources for the Power BI model.
// Each table reads a committed Parquet file from the repo via a single folder parameter, so the
// model is durable (no Snowflake) and portable (no hard-coded absolute path).
//
// SETUP (once, in Power BI Desktop):
//   1. Home → Transform data → Manage Parameters → New:
//        Name: GoldExportFolder   Type: Text
//        Current value: <your local clone>\app\gold_export
//        e.g. C:\dev\portfolio\tfl-data-engineering\app\gold_export
//   2. For each table below: Home → New Source → Blank Query → Advanced Editor → paste the block.
//   3. Rename each query to the table name (the comment header).
//
// Power BI reads Parquet natively via Parquet.Document — no gateway, no credentials.

// ── daily_journey_stats ──
let
    Source = Parquet.Document ( File.Contents ( GoldExportFolder & "\daily_journey_stats.parquet" ) )
in
    Source

// ── station_daily_flows ──
let
    Source = Parquet.Document ( File.Contents ( GoldExportFolder & "\station_daily_flows.parquet" ) )
in
    Source

// ── dim_station ──
let
    Source = Parquet.Document ( File.Contents ( GoldExportFolder & "\dim_station.parquet" ) )
in
    Source

// ── dim_date ──
let
    Source = Parquet.Document ( File.Contents ( GoldExportFolder & "\dim_date.parquet" ) )
in
    Source

// ── weather_daily ──
let
    Source = Parquet.Document ( File.Contents ( GoldExportFolder & "\weather_daily.parquet" ) )
in
    Source

// ── demand_deviation (median baseline) ──
let
    Source = Parquet.Document ( File.Contents ( GoldExportFolder & "\demand_deviation.parquet" ) )
in
    Source

// ── demand_deviation_ml (LightGBM baseline) ──
let
    Source = Parquet.Document ( File.Contents ( GoldExportFolder & "\demand_deviation_ml.parquet" ) )
in
    Source

// ── live_line_status ──
let
    Source = Parquet.Document ( File.Contents ( GoldExportFolder & "\live_line_status.parquet" ) )
in
    Source

// ── live_bikepoint ──
let
    Source = Parquet.Document ( File.Contents ( GoldExportFolder & "\live_bikepoint.parquet" ) )
in
    Source
