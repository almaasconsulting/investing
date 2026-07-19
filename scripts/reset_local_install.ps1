param(
    [string]$DataRoot = "C:\repo\InvestingData",
    [switch]$DeleteDataInsteadOfBackup,
    [switch]$KeepVirtualEnvironment,
    [switch]$KeepRuntimeConfig,
    [switch]$UnregisterStartupTasks,
    [switch]$StopRunningServices,
    [switch]$ResetPostgreSQL,
    [string]$PostgresHost = "",
    [int]$PostgresPort = 0,
    [string]$PostgresDatabase = "",
    [string]$PostgresUser = "",
    [string]$PostgresPassword = "",
    [string]$PostgresSchema = "",
    [switch]$ConfirmReset
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot).TrimEnd('\')
$VenvRoot = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot ".venv")).TrimEnd('\')
$RuntimeFile = Join-Path $RepoRoot ".runtime-env.ps1"

function Remove-DirectoryWithRetry([string]$Path) {
    for ($Attempt = 1; $Attempt -le 6; $Attempt++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return
        } catch {
            if ($Attempt -eq 6) { throw }
            Write-Warning "Windows is still releasing files under $Path; retry $Attempt/6 ..."
            Start-Sleep -Seconds 2
        }
    }
}

if (-not $ConfirmReset) {
    throw "Reset was not confirmed. Review the command, then add -ConfirmReset."
}
if ($DataRoot -in @("C:", $RepoRoot, (Split-Path $RepoRoot -Qualifier))) {
    throw "Refusing unsafe DataRoot: $DataRoot"
}
$DataPrefix = "$DataRoot\"
$RepoPrefix = "$RepoRoot\"
if ($RepoRoot.StartsWith($DataPrefix, [StringComparison]::OrdinalIgnoreCase) -or
    $DataRoot.StartsWith($RepoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "DataRoot must not contain or be inside the source repository: $DataRoot"
}
if ($VenvRoot -ne (Join-Path $RepoRoot ".venv")) {
    throw "Refusing unexpected virtual-environment path: $VenvRoot"
}

if ($UnregisterStartupTasks) {
    foreach ($TaskName in @("Investing Dagster", "Investing Streamlit")) {
        $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($Task) {
            Stop-ScheduledTask -InputObject $Task -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }
    }
}

function Get-ProjectServiceProcesses {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -match '^(python|pythonw|dagster|streamlit)(\.exe)?$' -and
        $_.CommandLine -and
        $_.CommandLine.IndexOf($RepoRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0
    }
}

$RunningProjectProcesses = @(Get-ProjectServiceProcesses)
if ($RunningProjectProcesses -and $StopRunningServices) {
    $RunningProjectProcesses | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    $RunningProjectProcesses = @(Get-ProjectServiceProcesses)
}
if ($RunningProjectProcesses) {
    $ProcessList = ($RunningProjectProcesses | ForEach-Object {
        "$($_.Name) PID=$($_.ProcessId)"
    }) -join ", "
    throw "Project Dagster/Streamlit processes are still running: $ProcessList. Stop them or add -StopRunningServices."
}

if ($ResetPostgreSQL) {
    # Reuse the installed runtime connection unless the caller supplied an override.
    if (Test-Path -LiteralPath $RuntimeFile) {
        . $RuntimeFile
    }
    if (-not $PostgresHost) { $PostgresHost = $env:INVESTING_POSTGRES_HOST }
    if (-not $PostgresHost) { $PostgresHost = "localhost" }
    if ($PostgresPort -le 0) {
        $PostgresPort = if ($env:INVESTING_POSTGRES_PORT) {
            [int]$env:INVESTING_POSTGRES_PORT
        } else { 5432 }
    }
    if (-not $PostgresDatabase) { $PostgresDatabase = $env:INVESTING_POSTGRES_DATABASE }
    if (-not $PostgresDatabase) { $PostgresDatabase = "investing" }
    if (-not $PostgresUser) { $PostgresUser = $env:INVESTING_POSTGRES_USER }
    if (-not $PostgresUser) { $PostgresUser = "investing" }
    if (-not $PostgresPassword) { $PostgresPassword = $env:INVESTING_POSTGRES_PASSWORD }
    if (-not $PostgresSchema) { $PostgresSchema = $env:INVESTING_POSTGRES_SCHEMA }
    if (-not $PostgresSchema) { $PostgresSchema = "main" }
    if ($PostgresSchema -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        throw "Unsafe PostgreSQL schema name: $PostgresSchema"
    }
    if ($PostgresUser -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        throw "Unsafe PostgreSQL role name: $PostgresUser"
    }
    if (-not $PostgresPassword) {
        $SecurePassword = Read-Host "Password for PostgreSQL role '$PostgresUser'" -AsSecureString
        $PasswordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
        try {
            $PostgresPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($PasswordPointer)
        } finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($PasswordPointer)
        }
    }

    $Psql = $null
    foreach ($Version in @("18", "17")) {
        $Candidate = "C:\Program Files\PostgreSQL\$Version\bin\psql.exe"
        if (Test-Path -LiteralPath $Candidate) {
            $Psql = $Candidate
            break
        }
    }
    if (-not $Psql) {
        $PsqlCommand = Get-Command psql -ErrorAction SilentlyContinue
        if ($PsqlCommand) { $Psql = $PsqlCommand.Source }
    }
    if (-not $Psql) {
        throw "PostgreSQL reset was requested, but psql.exe was not found."
    }

    $ResetSql = @"
DROP SCHEMA IF EXISTS gold CASCADE;
DROP SCHEMA IF EXISTS silver CASCADE;
DROP SCHEMA IF EXISTS bronze CASCADE;
DROP SCHEMA IF EXISTS `"$PostgresSchema`" CASCADE;
CREATE SCHEMA `"$PostgresSchema`" AUTHORIZATION `"$PostgresUser`";
"@
    $PreviousPassword = $env:PGPASSWORD
    try {
        $env:PGPASSWORD = $PostgresPassword
        & $Psql --host $PostgresHost --port $PostgresPort --username $PostgresUser `
            --dbname $PostgresDatabase --set ON_ERROR_STOP=1 --command $ResetSql
        if ($LASTEXITCODE -ne 0) {
            throw "Resetting PostgreSQL schemas failed with exit code $LASTEXITCODE."
        }
    } finally {
        $env:PGPASSWORD = $PreviousPassword
    }
    Write-Host "Deleted PostgreSQL application data from $PostgresDatabase (main/bronze/silver/gold schemas)."
}

if (Test-Path -LiteralPath $DataRoot) {
    if ($DeleteDataInsteadOfBackup) {
        Remove-DirectoryWithRetry $DataRoot
        Write-Host "Deleted data directory: $DataRoot"
    } else {
        $BackupPath = "$DataRoot.backup.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Move-Item -LiteralPath $DataRoot -Destination $BackupPath
        Write-Host "Moved existing data to: $BackupPath"
    }
}

if (-not $KeepVirtualEnvironment -and (Test-Path -LiteralPath $VenvRoot)) {
    Remove-DirectoryWithRetry $VenvRoot
    Write-Host "Deleted virtual environment: $VenvRoot"
}
if (-not $KeepRuntimeConfig -and (Test-Path -LiteralPath $RuntimeFile)) {
    Remove-Item -LiteralPath $RuntimeFile -Force
    Write-Host "Deleted runtime configuration: $RuntimeFile"
}

Write-Host "Reset complete. The source repository and PostgreSQL server/database were not deleted."
