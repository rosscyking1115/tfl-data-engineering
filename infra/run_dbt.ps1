# Run dbt with credentials loaded from .env (which is never committed).
# Usage: .\infra\run_dbt.ps1 build          (any dbt args pass through)
$repo = (Resolve-Path "$PSScriptRoot\..").Path
Get-Content "$repo\.env" | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*)=(.*)$') {
        [Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim())
    }
}
& "$repo\.venv\Scripts\dbt.exe" @args --project-dir "$repo\dbt" --profiles-dir "$repo\dbt"
exit $LASTEXITCODE
