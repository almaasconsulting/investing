# Storage computer setup

## Prerequisites

- Windows 10/11 or Windows Server with PowerShell 5.1 or newer.
- Python 3.12 recommended (3.11 is also suitable for the project dependencies).
- Git.
- Internet access to PyPI, Yahoo Finance, Investing.com, and stock-universe sources.
- Enough disk space for retained price history, Dagster logs, and backups.

Do not copy `.venv` from another computer. Clone/copy the source repository and let the installer create a local virtual environment.

## Install

```powershell
git clone <repository-url> C:\repo\investing
Set-Location C:\repo\investing
powershell -ExecutionPolicy Bypass -File .\scripts\install_storage_computer.ps1 `
  -DataRoot C:\repo\InvestingData `
  -InstallPostgreSQL
```

The installer:

1. Creates `.venv` and installs pinned/project dependencies there.
2. Clears `PYTHONPATH` for the process and enables `PYTHONNOUSERSITE`, preventing global packages from leaking into the venv.
3. Writes local runtime settings to ignored `.runtime-env.ps1`.
4. Initializes PostgreSQL storage.
5. validates and builds dbt models/tests.
6. Builds offline HTML documentation into `site\`.
7. Runs the Python test suite.

Optional switches:

```powershell
# Also register Dagster and Streamlit as logon tasks (may require elevated rights)
.\scripts\install_storage_computer.ps1 -DataRoot D:\InvestingData -RegisterStartupTasks

# Start both services after installation
.\scripts\install_storage_computer.ps1 -DataRoot D:\InvestingData -StartServices
```

## Install PostgreSQL automatically

Run PowerShell as an administrator:

```powershell
Set-Location C:\repo\investing
powershell -ExecutionPolicy Bypass -File .\scripts\install_storage_computer.ps1 `
  -DataRoot C:\repo\InvestingData `
  -InstallPostgreSQL `
  -PostgresVersion 18 `
  -PostgresHost localhost `
  -PostgresPort 5432 `
  -PostgresDatabase investing `
  -PostgresUser investing
```

The installer prompts for the application password, launches the official PostgreSQL Windows installer through `winget`, and then prompts for the `postgres` administrator password to create the application role and database. Do not put passwords directly in a saved command or PowerShell history.

If `winget` is unavailable, install PostgreSQL manually from the official Windows download page. Then rerun the platform installer without `-InstallPostgreSQL`, using the connection parameters documented below. For a remote PostgreSQL server, do not use `-InstallPostgreSQL`.

## Clean reinstall on this computer

For a completely clean rebuild, the reset command can permanently delete `C:\repo\InvestingData` and wipe the application schemas in PostgreSQL. This is irreversible:

1. Stop Streamlit and Dagster with `Ctrl+C` in both terminals.
2. Close other Python processes using this repository.
3. Run:

```powershell
Set-Location C:\repo\investing
.\scripts\reset_local_install.ps1 `
  -DataRoot C:\repo\InvestingData `
  -DeleteDataInsteadOfBackup `
  -ResetPostgreSQL `
  -StopRunningServices `
  -UnregisterStartupTasks `
  -PostgresDatabase investing `
  -PostgresUser investing `
  -ConfirmReset
```

The command reuses the PostgreSQL login from `.runtime-env.ps1` (or prompts for its password), drops and recreates the `main`, `bronze`, `silver`, and `gold` schemas, deletes the data directory, `.venv`, and `.runtime-env.ps1`, and leaves the PostgreSQL server, login, database, and source repository intact. Omit `-ResetPostgreSQL` only when PostgreSQL is not installed. This is the recommended reset when replacing the former exchange-wide universe with the curated index universe.

4. Run the automatic PostgreSQL installation command above.
5. Start Dagster and Streamlit as described below.
6. Run `universe_refresh_job`, one `stock_batch_refresh_job` partition, and `medallion_refresh_job`.
7. Verify Stock View, news, fundamentals, and Rankings. Keep the timestamped backup until several scheduled runs succeed.

## First start

Start Dagster and Streamlit in separate terminals:

```powershell
.\scripts\start_dagster.ps1
.\scripts\start_streamlit.ps1
```

Open Dagster at <http://localhost:3000>. The schedules are enabled by default. Run `universe_refresh_job` once if the stock catalog is empty. `continuous_stock_batch_schedule` then walks the entire universe in oldest-first partitioned batches, while `hourly_medallion_schedule` publishes available landing data through dbt.

Start Dagster before Streamlit. Streamlit reads PostgreSQL concurrently using short-lived connections; transaction isolation provides consistent committed reads while Dagster updates data.

Override schedule times in `.runtime-env.ps1`:

```powershell
$env:INVESTING_BATCH_CRON = '*/15 * * * *'
$env:INVESTING_DBT_CRON = '10 * * * *'
$env:INVESTING_TIMEZONE = 'Europe/Oslo'
```

## Configuration

PostgreSQL is the production installer default. Create the database and
login first, then run the installer with the connection parameters:

```powershell
$credential = Get-Credential -UserName investing
powershell -ExecutionPolicy Bypass -File .\scripts\install_storage_computer.ps1 `
  -DataRoot C:\repo\InvestingData `
  -PostgresHost localhost `
  -PostgresPort 5432 `
  -PostgresDatabase investing `
  -PostgresUser $credential.UserName `
  -PostgresPassword $credential.GetNetworkCredential().Password `
  -PostgresSslMode prefer
```

The installer stores these values in the ignored local `.runtime-env.ps1` so
scheduled services receive the same configuration. That file contains the
password in plain text: do not commit or share it, and restrict its Windows
file permissions. `INVESTING_DATABASE_URL` can be used instead for Python
storage access, but the component variables are still used by dbt.

| Variable | Default | Meaning |
|---|---:|---|
| `INVESTING_DATABASE_URL` | empty | Optional complete PostgreSQL URL; takes precedence for Python ingestion. |
| `INVESTING_POSTGRES_HOST` | `localhost` | PostgreSQL server hostname or IP address. |
| `INVESTING_POSTGRES_PORT` | `5432` | PostgreSQL TCP port. |
| `INVESTING_POSTGRES_DATABASE` | `investing` | PostgreSQL database name. |
| `INVESTING_POSTGRES_USER` | `investing` | PostgreSQL login name. |
| `INVESTING_POSTGRES_PASSWORD` | empty | PostgreSQL login password; keep it out of Git and logs. |
| `INVESTING_POSTGRES_SSLMODE` | `prefer` | PostgreSQL SSL mode, such as `prefer`, `require`, or `verify-full`. |
| `INVESTING_POSTGRES_SCHEMA` | `main` | Landing schema created for Python ingestion and used as the dbt source schema. |
| `DAGSTER_HOME` | under DataRoot | Dagster run history and schedule state. |
| `INVESTING_COUNTRIES` | US, Canada, Norway and ten European markets | Comma-separated universe countries. |
| `INVESTING_UNIVERSE_SOURCE` | `index` | Flagship national indexes plus US/Canadian REITs and dividend aristocrats. |
| `INVESTING_ANALYSIS_SCOPE` | `universe` | Price/analysis scope: `universe` or `watchlist`. |
| `INVESTING_CONTENT_SCOPE` | `universe` | News/statement scope: `universe` or `watchlist`. |
| `INVESTING_BATCH_SIZE` | `200` | Maximum oldest stocks processed per asset and partition run. |
| `INVESTING_BATCH_PARTITION_COUNT` | `50` | Stable Dagster hash buckets, averaging about 200 stocks for a 10,000-stock universe. |
| `INVESTING_FETCH_WORKERS` | `4` | Concurrent provider requests inside one ingestion asset (bounded to 1–16). |
| `INVESTING_BATCH_CRON` | every 15 minutes | Schedule for the next globally oldest partition. |
| `INVESTING_DBT_CRON` | hourly at minute 10 | Schedule for publishing dbt layers. |
| `INVESTING_CONTENT_MAX_STOCKS` | empty | Optional news/statement cap; empty processes all stocks. |
| `INVESTING_NEWS_COUNT` | `30` | Recent Yahoo news items requested per stock. |
| `INVESTING_DATA_SOURCE` | `auto` | `auto`, `yahoo`, or `investing`. |
| `INVESTING_ANALYSIS_DAYS` | `1825` | Retained analysis lookback. |
| `INVESTING_INCREMENTAL_OVERLAP_DAYS` | `7` | Re-fetch overlap for corrections. |
| `INVESTING_MAX_STOCKS` | empty | Optional price/analysis cap; empty processes all stocks. |
| `INVESTING_PROGRESS_EVERY` | `10` | Dagster progress-log interval in stocks. |
| `INVESTING_FULL_REFRESH` | `false` | Re-fetch complete history when true. |

Use `pg_dump` for PostgreSQL backups and retain the `dagster` directory and watchlist with the dump. Test restores periodically.

## Network access

The start scripts listen on all interfaces. If remote browser access is needed, allow only trusted LAN/VPN clients through Windows Firewall for TCP 3000 and 8501. Do not expose either development server directly to the public internet; use authentication and a reverse proxy for wider access.
