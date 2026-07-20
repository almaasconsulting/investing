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
$LockPath = Join-Path $env:DAGSTER_HOME "investing-dagster.lock"
$LockStream = $null
try {
    $LockStream = [System.IO.File]::Open(
        $LockPath,
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
} catch [System.IO.IOException] {
    throw "Dagster is already running for DAGSTER_HOME '$env:DAGSTER_HOME'. Stop the existing Dagster terminal before starting another instance."
}

try {
    # The exclusive file handle above protects all future launches. The port
    # check also detects an older process started before the lock was added.
    $PortInUse = $false
    $Client = [System.Net.Sockets.TcpClient]::new()
    try {
        $Connect = $Client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if ($Connect.AsyncWaitHandle.WaitOne(300)) {
            try {
                $Client.EndConnect($Connect)
                $PortInUse = $Client.Connected
            } catch [System.Net.Sockets.SocketException] {
                $PortInUse = $false
            }
        }
    } finally {
        $Client.Dispose()
    }
    if ($PortInUse) {
        throw "Port $Port is already in use. Dagster may already be running. Stop the existing instance or choose a different port."
    }

    $LockMetadata = @{
        pid = $PID
        started_at = (Get-Date).ToString("o")
        repository = $RepoRoot
        dagster_home = $env:DAGSTER_HOME
        port = $Port
    } | ConvertTo-Json -Compress
    $LockBytes = [System.Text.Encoding]::UTF8.GetBytes($LockMetadata)
    $LockStream.SetLength(0)
    $LockStream.Write($LockBytes, 0, $LockBytes.Length)
    $LockStream.Flush()

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
if ($LASTEXITCODE -ne 0) {
    throw "Dagster exited with code $LASTEXITCODE."
}
} finally {
    if ($null -ne $LockStream) {
        $LockStream.Dispose()
    }
}
