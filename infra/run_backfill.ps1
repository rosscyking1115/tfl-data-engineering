# Run the Spark backfill in the official Apache Spark container.
# Why Docker: Windows-native Spark needs winutils.exe/hadoop.dll for parquet writes
# (and Java 25, the system default here, removed APIs Hadoop still calls — JEP 486).
# Usage: .\infra\run_backfill.ps1 [-InputDir data/raw/usage-stats] [-DriverMem 8g]
param(
    [string]$InputDir = "data/raw/usage-stats",
    [string]$OutputDir = "data",
    [string]$DriverMem = "8g"
)
$repo = (Resolve-Path "$PSScriptRoot\..").Path
docker run --rm `
    -v "${repo}:/repo" `
    -w /repo `
    apache/spark:4.0.1-java21-python3 `
    /opt/spark/bin/spark-submit `
    --master "local[*]" `
    --driver-memory $DriverMem `
    spark/backfill.py --input $InputDir --output $OutputDir
exit $LASTEXITCODE
