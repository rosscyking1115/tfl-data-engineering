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

// ── certified_adr0009_evidence (rigor-owned, disconnected certificate table) ──
let
    Source = Json.Document ( File.Contents ( GoldExportFolder & "\analysis_rigor.json" ) ),
    Certificate = Source[certificate],
    Headline = Source[headline],
    Output = #table(
        {"evidence_artifact", "certificate_id", "evidence_version", "adr_id", "claim_class", "permitted_claim", "comparator_family", "cited_strike_seed", "station_day_evidence", "min_expected_departures", "headline_ratio", "ci95_lo", "ci95_hi", "n_events"},
        {{"app/gold_export/analysis_rigor.json", Certificate[certificate_id], Certificate[evidence_version], Certificate[adr_id], Certificate[claim_class], Certificate[permitted_claim], Certificate[primary_specification][comparator_family], Certificate[primary_specification][strike_seed], "app/gold_export/demand_deviation.parquet", Certificate[primary_specification][min_expected_departures], Headline[median_ratio], Headline[ci95_lo], Headline[ci95_hi], Headline[n_events]}}
    )
in
    Output

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
