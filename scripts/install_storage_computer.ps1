param(
    [string]$DataRoot = "",
    [string]$DatabaseUrl = "",
    [string]$PostgresHost = "localhost",
    [ValidateRange(1, 65535)]
    [int]$PostgresPort = 5432,
    [string]$PostgresDatabase = "investing",
    [string]$PostgresUser = "investing",
    [string]$PostgresPassword = "",
    [string]$PostgresSslMode = "prefer",
    [string]$PostgresSchema = "main",
    [switch]$InstallPostgreSQL,
    [ValidateSet("17", "18")]
    [string]$PostgresVersion = "18",
    [string]$PostgresAdminUser = "postgres",
    [string]$PostgresAdminPassword = "",
    [switch]$ResetPostgreSQLData,
    [switch]$RegisterStartupTasks,
    [switch]$StartServices,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
function Assert-NativeSuccess([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE." }
}
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $DataRoot) { $DataRoot = Join-Path $RepoRoot "runtime" }
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)
$VenvRoot = Join-Path $RepoRoot ".venv"
$Python = Join-Path $VenvRoot "Scripts\python.exe"

if ($DatabaseUrl) {
    $ParsedDatabaseUrl = [Uri]$DatabaseUrl
    if ($ParsedDatabaseUrl.Scheme -notin @("postgresql", "postgres")) {
        throw "DatabaseUrl must use the postgresql:// scheme."
    }
    $PostgresHost = $ParsedDatabaseUrl.Host
    if (-not $ParsedDatabaseUrl.IsDefaultPort) { $PostgresPort = $ParsedDatabaseUrl.Port }
    $PostgresDatabase = [Uri]::UnescapeDataString($ParsedDatabaseUrl.AbsolutePath.TrimStart("/"))
    $UserInfo = $ParsedDatabaseUrl.UserInfo -split ":", 2
    if ($UserInfo.Count -ge 1) { $PostgresUser = [Uri]::UnescapeDataString($UserInfo[0]) }
    if ($UserInfo.Count -eq 2) { $PostgresPassword = [Uri]::UnescapeDataString($UserInfo[1]) }
    foreach ($Pair in $ParsedDatabaseUrl.Query.TrimStart("?") -split "&") {
        $Parts = $Pair -split "=", 2
        if ($Parts.Count -eq 2 -and $Parts[0] -eq "sslmode") {
            $PostgresSslMode = [Uri]::UnescapeDataString($Parts[1])
        }
    }
}
if (-not $DatabaseUrl -and -not $PostgresPassword) {
    $SecurePassword = Read-Host "Password for PostgreSQL application role '$PostgresUser'" -AsSecureString
    $PasswordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
    try { $PostgresPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($PasswordPointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($PasswordPointer) }
}

if ($InstallPostgreSQL) {
    & (Join-Path $PSScriptRoot "install_postgresql.ps1") `
        -PostgresVersion $PostgresVersion `
        -PostgresHost $PostgresHost `
        -PostgresPort $PostgresPort `
        -PostgresDatabase $PostgresDatabase `
        -PostgresUser $PostgresUser `
        -PostgresPassword $PostgresPassword `
        -PostgresAdminUser $PostgresAdminUser `
        -PostgresAdminPassword $PostgresAdminPassword
}

Write-Host "Installing the Investing medallion platform in $RepoRoot"
Write-Host "Persistent data directory: $DataRoot"
Write-Host "PostgreSQL server: $PostgresHost`:$PostgresPort / $PostgresDatabase"
New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DataRoot "dagster") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DataRoot "logs") | Out-Null
$DagsterConfig = Join-Path $DataRoot "dagster\dagster.yaml"
if (-not (Test-Path $DagsterConfig)) {
    New-Item -ItemType File -Path $DagsterConfig | Out-Null
}

if (Test-Path $Python) {
    & $Python -c "import sys; print(sys.executable)" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        $BrokenVenv = "$VenvRoot.broken.$(Get-Date -Format 'yyyyMMddHHmmss')"
        Write-Warning "The existing .venv points to a missing Python. Moving it to $BrokenVenv."
        Move-Item -LiteralPath $VenvRoot -Destination $BrokenVenv
    }
}

if (-not (Test-Path $Python)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv $VenvRoot
        if ($LASTEXITCODE -ne 0) {
            & py -3.11 -m venv $VenvRoot
        }
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $VenvRoot
    } else {
        throw "Python 3.11 or 3.12 was not found. Install Python, then rerun this script."
    }
}
if (-not (Test-Path $Python)) { throw "Virtual environment creation failed." }

$env:PYTHONPATH = $null
$env:PYTHONNOUSERSITE = "1"
$env:INVESTING_DATABASE_URL = $DatabaseUrl
$env:INVESTING_POSTGRES_HOST = $PostgresHost
$env:INVESTING_POSTGRES_PORT = [string]$PostgresPort
$env:INVESTING_POSTGRES_DATABASE = $PostgresDatabase
$env:INVESTING_POSTGRES_USER = $PostgresUser
$env:INVESTING_POSTGRES_PASSWORD = $PostgresPassword
$env:INVESTING_POSTGRES_SSLMODE = $PostgresSslMode
$env:INVESTING_POSTGRES_SCHEMA = $PostgresSchema
$env:INVESTING_WATCHLIST_PATH = Join-Path $DataRoot "watchlist.csv"
$env:INVESTING_ANALYSIS_SCOPE = "universe"
$env:INVESTING_CONTENT_SCOPE = "universe"
$env:INVESTING_UNIVERSE_SOURCE = "index"
$env:INVESTING_BATCH_SIZE = "200"
$env:INVESTING_BATCH_PARTITION_COUNT = "50"
$env:INVESTING_FETCH_WORKERS = "4"
$env:INVESTING_PROGRESS_EVERY = "10"
$env:INVESTING_INCREMENTAL_OVERLAP_DAYS = "7"
$env:DAGSTER_HOME = Join-Path $DataRoot "dagster"

$RuntimeContent = @'
$env:INVESTING_WATCHLIST_PATH = '{0}'
$env:INVESTING_DATABASE_URL = '{1}'
$env:INVESTING_POSTGRES_HOST = '{2}'
$env:INVESTING_POSTGRES_PORT = '{3}'
$env:INVESTING_POSTGRES_DATABASE = '{4}'
$env:INVESTING_POSTGRES_USER = '{5}'
$env:INVESTING_POSTGRES_PASSWORD = '{6}'
$env:INVESTING_POSTGRES_SSLMODE = '{7}'
$env:INVESTING_POSTGRES_SCHEMA = '{8}'
$env:INVESTING_ANALYSIS_SCOPE = 'universe'
$env:INVESTING_CONTENT_SCOPE = 'universe'
$env:INVESTING_UNIVERSE_SOURCE = 'index'
$env:INVESTING_BATCH_SIZE = '200'
$env:INVESTING_BATCH_PARTITION_COUNT = '50'
$env:INVESTING_FETCH_WORKERS = '4'
$env:INVESTING_BATCH_CRON = '*/15 * * * *'
$env:INVESTING_DBT_CRON = '10 * * * *'
$env:INVESTING_NEWS_COUNT = '30'
$env:INVESTING_PROGRESS_EVERY = '10'
$env:INVESTING_COUNTRIES = 'norway,united states,canada,united kingdom,france,germany,switzerland,sweden,netherlands,italy,spain,denmark,finland'
$env:INVESTING_DATA_SOURCE = 'auto'
$env:INVESTING_INCREMENTAL_OVERLAP_DAYS = '7'
$env:DAGSTER_HOME = '{9}'
'@ -f (
    $env:INVESTING_WATCHLIST_PATH -replace "'", "''"
), (
    $env:INVESTING_DATABASE_URL -replace "'", "''"
), (
    $env:INVESTING_POSTGRES_HOST -replace "'", "''"
), (
    $env:INVESTING_POSTGRES_PORT -replace "'", "''"
), (
    $env:INVESTING_POSTGRES_DATABASE -replace "'", "''"
), (
    $env:INVESTING_POSTGRES_USER -replace "'", "''"
), (
    $env:INVESTING_POSTGRES_PASSWORD -replace "'", "''"
), (
    $env:INVESTING_POSTGRES_SSLMODE -replace "'", "''"
), (
    $env:INVESTING_POSTGRES_SCHEMA -replace "'", "''"
), (
    $env:DAGSTER_HOME -replace "'", "''"
)
Set-Content -Path (Join-Path $RepoRoot ".runtime-env.ps1") -Value $RuntimeContent -Encoding UTF8

# Keep ingestion runs sequential by default to avoid provider throttling.
@'
run_queue:
  max_concurrent_runs: 1
'@ | Set-Content -Path (Join-Path $env:DAGSTER_HOME "dagster.yaml") -Encoding UTF8

if (-not (Test-Path $env:INVESTING_WATCHLIST_PATH)) {
    $SourceWatchlist = Join-Path $RepoRoot "watchlist.csv"
    if (Test-Path $SourceWatchlist) {
        Copy-Item $SourceWatchlist $env:INVESTING_WATCHLIST_PATH
    }
}

Write-Host "Installing Python dependencies into .venv ..."
& $Python -m pip install --upgrade pip setuptools wheel
Assert-NativeSuccess "pip bootstrap"
& $Python -m pip install -r (Join-Path $RepoRoot "requirements.txt")
Assert-NativeSuccess "dependency installation"
& $Python -c "import psycopg; print('psycopg', psycopg.__version__)"
Assert-NativeSuccess "psycopg validation"

if ($ResetPostgreSQLData) {
    Write-Warning "ResetPostgreSQLData is enabled. All application tables in the landing, bronze, silver, and gold schemas will be deleted."
    & $Python (Join-Path $PSScriptRoot "reset_postgresql_data.py")
    Assert-NativeSuccess "PostgreSQL application-data reset"
}

Write-Host "Initializing PostgreSQL storage ..."
& $Python -c "from investing.db.store import init_db; con=init_db(); con.close(); print('Database initialized')"
Assert-NativeSuccess "PostgreSQL initialization"

Write-Host "Validating dbt and building the medallion schemas ..."
& (Join-Path $VenvRoot "Scripts\dbt.exe") debug --project-dir (Join-Path $RepoRoot "analytics") --profiles-dir (Join-Path $RepoRoot "analytics")
Assert-NativeSuccess "dbt debug"
& (Join-Path $PSScriptRoot "run_dbt.ps1")
Assert-NativeSuccess "dbt build"

Write-Host "Validating Dagster definitions and native dbt assets ..."
& $Python -c "from investing.orchestration.definitions import defs; print(f'Dagster loaded {len(defs.resolve_asset_graph().get_all_asset_keys())} assets')"
Assert-NativeSuccess "Dagster definition validation"

Write-Host "Building local HTML documentation ..."
& $Python -m mkdocs build --clean --config-file (Join-Path $RepoRoot "mkdocs.yml")
Assert-NativeSuccess "documentation build"

if (-not $SkipTests) {
    Write-Host "Running tests ..."
    & $Python -m unittest discover -s (Join-Path $RepoRoot "tests") -v
    Assert-NativeSuccess "test suite"
}

if ($RegisterStartupTasks) {
    $DagsterAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $PSScriptRoot 'start_dagster.ps1')`""
    $StreamlitAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $PSScriptRoot 'start_streamlit.ps1')`""
    $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    Register-ScheduledTask -TaskName "Investing Dagster" -Action $DagsterAction -Trigger $Trigger -Description "Dagster orchestration for Investing" -Force | Out-Null
    Register-ScheduledTask -TaskName "Investing Streamlit" -Action $StreamlitAction -Trigger $Trigger -Description "Streamlit UI for Investing" -Force | Out-Null
    Write-Host "Registered logon tasks for Dagster and Streamlit."
}

Write-Host ""
Write-Host "Installation complete."
Write-Host "Start Dagster:   .\scripts\start_dagster.ps1"
Write-Host "Start Streamlit: .\scripts\start_streamlit.ps1"
Write-Host "Dagster UI:      http://localhost:3000"
Write-Host "Streamlit UI:    http://localhost:8501"

if ($StartServices) {
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "start_dagster.ps1")
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $PSScriptRoot "start_streamlit.ps1")
}
