param([int]$Port = 8501)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "load_runtime_env.ps1")
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "The virtual environment is missing. Run scripts\install_storage_computer.ps1 first."
}
Set-Location $RepoRoot
& $Python -m streamlit run streamlit_app.py --server.port $Port
