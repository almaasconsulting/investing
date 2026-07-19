param(
    [ValidateSet("17", "18")]
    [string]$PostgresVersion = "18",
    [string]$PostgresHost = "localhost",
    [ValidateRange(1, 65535)]
    [int]$PostgresPort = 5432,
    [string]$PostgresDatabase = "investing",
    [string]$PostgresUser = "investing",
    [string]$PostgresPassword = "",
    [string]$PostgresAdminUser = "postgres",
    [string]$PostgresAdminPassword = ""
)

$ErrorActionPreference = "Stop"

function ConvertFrom-SecureValue([Security.SecureString]$Value) {
    $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer) }
}

function Find-PostgresTool([string]$Name, [string]$Version) {
    $VersionPath = "C:\Program Files\PostgreSQL\$Version\bin\$Name.exe"
    if (Test-Path -LiteralPath $VersionPath) { return $VersionPath }
    $Command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($Command -and $Name -eq "psql") {
        $VersionOutput = & $Command.Source --version 2>$null
        if ($VersionOutput -match "PostgreSQL\) $([regex]::Escape($Version))\.") {
            return $Command.Source
        }
    }
    return $null
}

if ($PostgresHost -notin @("localhost", "127.0.0.1", "::1")) {
    throw "Automatic installation can provision only a local PostgreSQL server."
}
foreach ($Identifier in @($PostgresDatabase, $PostgresUser, $PostgresAdminUser)) {
    if ($Identifier -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        throw "Invalid PostgreSQL database or role name: $Identifier"
    }
}

$Psql = Find-PostgresTool "psql" $PostgresVersion
if (-not $Psql) {
    $Winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $Winget) {
        throw "winget is unavailable. Install PostgreSQL from https://www.postgresql.org/download/windows/ and rerun the installer."
    }
    Write-Host "Installing PostgreSQL $PostgresVersion. Complete the official installer and remember the postgres administrator password."
    & $Winget.Source install --exact --id "PostgreSQL.PostgreSQL.$PostgresVersion" --source winget --interactive --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL installation failed with exit code $LASTEXITCODE." }
    $Psql = Find-PostgresTool "psql" $PostgresVersion
}
if (-not $Psql) { throw "PostgreSQL is installed, but psql.exe could not be found." }
$Createdb = Join-Path (Split-Path $Psql) "createdb.exe"

$Service = Get-Service -Name "postgresql-x64-$PostgresVersion" -ErrorAction SilentlyContinue
if ($Service -and $Service.Status -ne "Running") {
    Start-Service -Name $Service.Name
    $Service.WaitForStatus("Running", [TimeSpan]::FromSeconds(60))
}
$Listening = $false
for ($Attempt = 1; $Attempt -le 30; $Attempt++) {
    if (Test-NetConnection -ComputerName $PostgresHost -Port $PostgresPort -InformationLevel Quiet -WarningAction SilentlyContinue) {
        $Listening = $true
        break
    }
    Start-Sleep -Seconds 2
}
if (-not $Listening) {
    throw "PostgreSQL $PostgresVersion was installed but did not start listening on ${PostgresHost}:${PostgresPort}."
}

if (-not $PostgresPassword) {
    $PostgresPassword = ConvertFrom-SecureValue (Read-Host "Password for application role '$PostgresUser'" -AsSecureString)
}
if (-not $PostgresAdminPassword) {
    $PostgresAdminPassword = ConvertFrom-SecureValue (Read-Host "Password for PostgreSQL administrator '$PostgresAdminUser'" -AsSecureString)
}

$EscapedPassword = $PostgresPassword.Replace("'", "''")
$RoleSql = @'
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{0}') THEN
        CREATE ROLE "{0}" LOGIN PASSWORD '{1}';
    ELSE
        ALTER ROLE "{0}" WITH LOGIN PASSWORD '{1}';
    END IF;
END
$$;
'@ -f $PostgresUser, $EscapedPassword

$PreviousPassword = $env:PGPASSWORD
try {
    $env:PGPASSWORD = $PostgresAdminPassword
    & $Psql --host $PostgresHost --port $PostgresPort --username $PostgresAdminUser --dbname postgres --set ON_ERROR_STOP=1 --command $RoleSql
    if ($LASTEXITCODE -ne 0) { throw "Creating the PostgreSQL application role failed." }

    $DatabaseExists = & $Psql --host $PostgresHost --port $PostgresPort --username $PostgresAdminUser --dbname postgres --tuples-only --no-align --command "SELECT 1 FROM pg_database WHERE datname = '$PostgresDatabase'"
    if ($LASTEXITCODE -ne 0) { throw "Checking the PostgreSQL application database failed." }
    if (-not ($DatabaseExists | Where-Object { $_.Trim() -eq "1" })) {
        & $Createdb --host $PostgresHost --port $PostgresPort --username $PostgresAdminUser --owner $PostgresUser $PostgresDatabase
        if ($LASTEXITCODE -ne 0) { throw "Creating the PostgreSQL application database failed." }
    }
} finally {
    $env:PGPASSWORD = $PreviousPassword
}

Write-Host "PostgreSQL ready: ${PostgresHost}:${PostgresPort}; database=$PostgresDatabase; user=$PostgresUser"
