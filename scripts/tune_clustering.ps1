param(
    [int]$Days = 730,
    [int]$MaxStocks = 100,
    [int]$MinObservations = 120,
    [string]$Countries = "",
    [string]$Output = "reports\cluster_tuning.json",
    [string]$HtmlOutput = "reports\cluster_tuning.html"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "load_runtime_env.ps1")

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Program = Join-Path $PSScriptRoot "tune_clustering.py"
$Arguments = @(
    $Program,
    "--days", $Days,
    "--max-stocks", $MaxStocks,
    "--min-observations", $MinObservations,
    "--output", $Output,
    "--html-output", $HtmlOutput
)
if ($Countries.Trim()) {
    $Arguments += @("--countries", $Countries)
}

& $Python @Arguments
if ($LASTEXITCODE -ne 0) {
    throw "Clustering tuner failed with exit code $LASTEXITCODE."
}
