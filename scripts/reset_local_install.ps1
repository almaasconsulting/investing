param(
    [string]$DataRoot = "C:\repo\InvestingData",
    [switch]$DeleteDataInsteadOfBackup,
    [switch]$KeepVirtualEnvironment,
    [switch]$KeepRuntimeConfig,
    [switch]$UnregisterStartupTasks,
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
if ($VenvRoot -ne (Join-Path $RepoRoot ".venv")) {
    throw "Refusing unexpected virtual-environment path: $VenvRoot"
}

$RunningPython = Get-Process python, pythonw, dagster, streamlit -ErrorAction SilentlyContinue
if ($RunningPython) {
    throw "Python/Dagster/Streamlit processes are still running. Stop both services and rerun the reset."
}

if ($UnregisterStartupTasks) {
    foreach ($TaskName in @("Investing Dagster", "Investing Streamlit")) {
        if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }
    }
}

if (Test-Path -LiteralPath $DataRoot) {
    if ($DeleteDataInsteadOfBackup) {
        Remove-Item -LiteralPath $DataRoot -Recurse -Force
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
