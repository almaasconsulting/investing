$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeFile = Join-Path $RepoRoot ".runtime-env.ps1"

if (Test-Path $RuntimeFile) {
    . $RuntimeFile
}

# Prevent globally installed packages from leaking into the project venv.
$env:PYTHONPATH = $null
$env:PYTHONNOUSERSITE = "1"
$VenvScripts = Join-Path $RepoRoot ".venv\Scripts"
if (-not (($env:PATH -split ";") -contains $VenvScripts)) {
    $env:PATH = "$VenvScripts;$env:PATH"
}

if (-not $env:INVESTING_POSTGRES_HOST) { $env:INVESTING_POSTGRES_HOST = "localhost" }
if (-not $env:INVESTING_POSTGRES_PORT) { $env:INVESTING_POSTGRES_PORT = "5432" }
if (-not $env:INVESTING_POSTGRES_DATABASE) { $env:INVESTING_POSTGRES_DATABASE = "investing" }
if (-not $env:INVESTING_POSTGRES_USER) { $env:INVESTING_POSTGRES_USER = "investing" }
if (-not $env:INVESTING_POSTGRES_SSLMODE) { $env:INVESTING_POSTGRES_SSLMODE = "prefer" }
if (-not $env:INVESTING_POSTGRES_SCHEMA) { $env:INVESTING_POSTGRES_SCHEMA = "main" }
if (-not $env:DAGSTER_HOME) {
    $env:DAGSTER_HOME = Join-Path $RepoRoot ".dagster"
}

New-Item -ItemType Directory -Force -Path $env:DAGSTER_HOME | Out-Null
