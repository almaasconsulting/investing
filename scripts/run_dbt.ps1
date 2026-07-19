param([switch]$FullRefresh)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "load_runtime_env.ps1")
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Dbt = Join-Path $RepoRoot ".venv\Scripts\dbt.exe"
if (-not (Test-Path $Dbt)) {
    throw "dbt is not installed. Run scripts\install_storage_computer.ps1 first."
}
$Arguments = @("build", "--project-dir", (Join-Path $RepoRoot "analytics"), "--profiles-dir", (Join-Path $RepoRoot "analytics"))
if ($FullRefresh) { $Arguments += "--full-refresh" }
& $Dbt @Arguments
