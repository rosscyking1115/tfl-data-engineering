$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
$cases = @(
    "normalize-five-variants",
    "duplicate-replay",
    "correction-replaces-period",
    "incompatible-preserves-state",
    "dst-ambiguity-rejected"
)

New-Item -ItemType Directory -Force "$PSScriptRoot\evidence\spark" | Out-Null
foreach ($case in $cases) {
    docker run --rm `
        -v "${repo}:/repo" `
        -w /repo `
        apache/spark:4.0.1-java21-python3 `
        /opt/spark/bin/spark-submit `
        --master "local[2]" `
        benchmark/gate0/spike/runner.py `
        --engine spark `
        --case "benchmark/gate0/cases/${case}.json" `
        --output "benchmark/gate0/evidence/spark/${case}.json"
    if ($LASTEXITCODE -ne 0) {
        throw "Spark case failed: $case"
    }
}

& "$repo\.venv\Scripts\python.exe" -m benchmark.gate0.spike.compare_outputs
exit $LASTEXITCODE
