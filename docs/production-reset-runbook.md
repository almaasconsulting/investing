# Production computer clean reset

This runbook makes the production computer match a newly installed version of
the Investing platform. It permanently removes the existing runtime data and
rebuilds PostgreSQL, dbt, Dagster, and Streamlit from the current source code.

## What this deletes

The reset command permanently deletes:

- `C:\repo\InvestingData`, including Dagster history and logs;
- the repository's `.venv` directory;
- the ignored `.runtime-env.ps1` configuration file;
- all application tables in the PostgreSQL `main`, `bronze`, `silver`, and
  `gold` schemas.

It does not delete the PostgreSQL server, PostgreSQL login, PostgreSQL
database, or `C:\repo\investing` source repository.

## 1. Prepare

Before starting, make sure that:

- the updated version has been committed and pushed, or copied to the
  production computer;
- you know the password for the PostgreSQL `investing` login;
- the production computer has Python 3.11 or 3.12 installed outside `.venv`;
- you have an Administrator PowerShell window if scheduled tasks were used.

Do not continue if any old data must be retained. The commands below do not
create a backup.

## 2. Stop the old services

Open PowerShell as Administrator and run:

```powershell
Set-Location C:\repo\investing

foreach ($name in "Investing Dagster", "Investing Streamlit") {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($task) {
        Stop-ScheduledTask -InputObject $task -ErrorAction SilentlyContinue
    }
}

Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -match '^(python|pythonw|dagster|streamlit)(\.exe)?$' -and
        $_.CommandLine -like '*C:\repo\investing*'
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
    }
```

Confirm that no repository services remain:

```powershell
Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -and $_.CommandLine -like '*C:\repo\investing*' -and
        $_.Name -match '^(python|pythonw|dagster|streamlit)(\.exe)?$'
    } |
    Select-Object Name, ProcessId, CommandLine
```

The command should return no rows.

## 3. Update the source code

When production uses Git and has no local source changes:

```powershell
Set-Location C:\repo\investing
git status --short
git pull --ff-only origin main
```

Review any output from `git status` before pulling. Do not discard production
changes unless they are known to be obsolete. If Git is not used, copy the
new repository files into `C:\repo\investing` before continuing, but do not
copy another computer's `.venv` or `.runtime-env.ps1`.

## 4. Delete runtime data and wipe PostgreSQL

Run the updated reset script:

```powershell
Set-Location C:\repo\investing

powershell -ExecutionPolicy Bypass `
  -File .\scripts\reset_local_install.ps1 `
  -DataRoot C:\repo\InvestingData `
  -DeleteDataInsteadOfBackup `
  -ResetPostgreSQL `
  -StopRunningServices `
  -UnregisterStartupTasks `
  -ConfirmReset
```

The script loads the existing PostgreSQL connection from
`.runtime-env.ps1` before deleting it. If no stored password is available, it
prompts for the `investing` PostgreSQL password without displaying it.

Expected completion messages include:

- PostgreSQL application schemas deleted and recreated;
- `C:\repo\InvestingData` deleted;
- `.venv` deleted;
- `.runtime-env.ps1` deleted;
- source repository not deleted.

## 5. Reinstall the platform

PostgreSQL is already installed, so do not use `-InstallPostgreSQL`:

```powershell
Set-Location C:\repo\investing

powershell -ExecutionPolicy Bypass `
  -File .\scripts\install_storage_computer.ps1 `
  -DataRoot C:\repo\InvestingData `
  -PostgresHost localhost `
  -PostgresPort 5432 `
  -PostgresDatabase investing `
  -PostgresUser investing `
  -PostgresSchema main `
  -RegisterStartupTasks
```

Enter the existing `investing` PostgreSQL password when prompted. The installer
creates a new `.venv`, installs dependencies, writes `.runtime-env.ps1`, creates
the landing tables, builds dbt models, validates Dagster, builds HTML
documentation, and runs the test suite.

If the PostgreSQL login or database no longer exists, rerun the installer with
`-InstallPostgreSQL`; this also requires the PostgreSQL administrator password.

## 6. Start Dagster and Streamlit

Use two PowerShell windows.

Window 1:

```powershell
Set-Location C:\repo\investing
.\scripts\start_dagster.ps1
```

Window 2:

```powershell
Set-Location C:\repo\investing
.\scripts\start_streamlit.ps1
```

Open:

- Dagster: <http://localhost:3000>
- Streamlit: <http://localhost:8501>

## 7. Initialize production data

In Dagster:

1. Run `universe_refresh_job` once and confirm success.
2. Run one partition of `stock_batch_refresh_job` and confirm that both Bronze
   assets succeed.
3. Run `medallion_refresh_job` and confirm the dbt Silver and Gold assets
   succeed.
4. Enable `daily_universe_schedule`, `continuous_stock_batch_schedule`, and
   `hourly_medallion_schedule` if they are disabled.

Dagster then processes the full stock universe incrementally, selecting
never-run stocks first and then the oldest previously attempted stocks.

In Streamlit, use **Load Saved Analysis** for the full universe. Do not use
**Run Analysis** with every stock selected; that performs synchronous fetching
inside Streamlit and duplicates Dagster's work.

## Troubleshooting

If reset still reports running services, list the matching processes:

```powershell
Get-CimInstance Win32_Process |
    Where-Object {
        $_.CommandLine -and $_.CommandLine -like '*C:\repo\investing*'
    } |
    Select-Object Name, ProcessId, CommandLine
```

If PostgreSQL schema reset fails, confirm that PostgreSQL is running and that
the `investing` login owns the application schemas. Do not manually delete
PostgreSQL data files from `C:\Program Files\PostgreSQL`.
