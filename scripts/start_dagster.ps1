param([int]$Port = 3000)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "load_runtime_env.ps1")
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Dagster = Join-Path $RepoRoot ".venv\Scripts\dagster.exe"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Dagster)) {
    throw "Dagster is not installed. Run scripts\install_storage_computer.ps1 first."
}
Set-Location $RepoRoot
$env:PYTHONLEGACYWINDOWSSTDIO = "1"
if (-not (Test-Path $env:DAGSTER_HOME)) {
    New-Item -ItemType Directory -Force -Path $env:DAGSTER_HOME | Out-Null
}
$DagsterConfig = Join-Path $env:DAGSTER_HOME "dagster.yaml"
if (-not (Test-Path $DagsterConfig)) {
@'
run_queue:
  max_concurrent_runs: 1
'@ | Set-Content -Path $DagsterConfig -Encoding UTF8
}
& $Python -c "from investing.orchestration.definitions import defs; print(f'Validated {len(defs.resolve_asset_graph().get_all_asset_keys())} Dagster assets')"
if ($LASTEXITCODE -ne 0) {
    throw "Dagster definition validation failed. Fix the import error before starting services."
}
& $Dagster dev -w (Join-Path $RepoRoot "workspace.yaml") -h 0.0.0.0 -p $Port
