[CmdletBinding()]
param(
    [ValidateSet("Validate", "DuckDB", "Spark", "Compare", "All")]
    [string]$Command = "All",
    [string]$OutputRoot = ".benchmark-output"
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
$OutputRoot = [System.IO.Path]::GetFullPath((Join-Path $RepositoryRoot $OutputRoot))
$SparkImage = "apache/spark:4.0.1-java21-python3@sha256:fb5c5e61e7bb1be94b7f3a31afe1f73c5b4d20b6008f4ffa7278fc085da08a9e"

function Invoke-Validate {
    & $Python -m benchmark.reliability_reference validate
    if ($LASTEXITCODE -ne 0) { throw "Benchmark validation failed." }
}

function Invoke-DuckDB {
    $Output = Join-Path $OutputRoot "duckdb"
    New-Item -ItemType Directory -Force -Path $Output | Out-Null
    & $Python -m benchmark.reliability_reference run --engine duckdb --scenario all --output $Output
    if ($LASTEXITCODE -ne 0) { throw "DuckDB conformance failed." }
}

function Invoke-Spark {
    $Output = Join-Path $OutputRoot "spark"
    New-Item -ItemType Directory -Force -Path $Output | Out-Null
    docker run --rm `
        --mount "type=bind,source=$RepositoryRoot,target=/repo,readonly" `
        --mount "type=bind,source=$Output,target=/out" `
        $SparkImage /opt/spark/bin/spark-submit /repo/tests/spark_reference_check.py /out
    if ($LASTEXITCODE -ne 0) { throw "Spark conformance failed." }
}

function Invoke-Compare {
    $DuckDB = Join-Path $OutputRoot "duckdb"
    $Spark = Join-Path $OutputRoot "spark"
    $Comparison = Join-Path $OutputRoot "comparison"
    & $Python -m benchmark.reliability_reference compare --duckdb $DuckDB --spark $Spark --output $Comparison
    if ($LASTEXITCODE -ne 0) { throw "Semantic comparison failed." }
}

switch ($Command) {
    "Validate" { Invoke-Validate }
    "DuckDB" { Invoke-Validate; Invoke-DuckDB }
    "Spark" { Invoke-Validate; Invoke-Spark }
    "Compare" { Invoke-Compare }
    "All" { Invoke-Validate; Invoke-DuckDB; Invoke-Spark; Invoke-Compare }
}
