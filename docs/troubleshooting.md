# Troubleshooting

## A package imports from outside `.venv`

All provided scripts clear `PYTHONPATH` and set `PYTHONNOUSERSITE=1`. Verify:

```powershell
.\scripts\load_runtime_env.ps1
.\.venv\Scripts\python.exe -c "import sys, typing_extensions; print(sys.executable); print(typing_extensions.__file__)"
```

Both paths should be under the repository `.venv`. If not, remove the user/machine `PYTHONPATH` that points at a global `site-packages`, reopen PowerShell, and rerun the installer.

## Investing.com reports `No module named pkg_resources`

The project includes a compatibility loader for `investpy` that replaces the two
legacy `pkg_resources` helpers it uses when necessary. It also suppresses only
investpy's own deprecation warning, so modern setuptools releases can be used.
Pull the latest code and rerun the storage-computer installer. If
`.venv\Scripts\python.exe` says its base Python executable is missing, reinstall
Python 3.12 first; virtual environments depend on that installation and cannot be
repaired only with `pip`.

## Installer file not found

Run from the repository root and verify:

```powershell
Test-Path .\scripts\install_storage_computer.ps1
```

If false, update/clone the revision containing the medallion implementation.

## Dagster does not load

```powershell
.\scripts\load_runtime_env.ps1
.\.venv\Scripts\python.exe -c "from investing.orchestration.definitions import defs; print('definitions loaded')"
```

Confirm `workspace.yaml` exists and that Dagster was installed into `.venv`.

## dbt cannot connect to PostgreSQL

Run `scripts\load_runtime_env.ps1`, then verify the host, port, database, user, password, SSL mode, and schema variables. Test with `scripts\run_dbt.ps1` and inspect `dbt debug` output. Confirm the PostgreSQL service is running and that its firewall and `pg_hba.conf` permit the storage-computer connection.

## No Gold rows

Gold facts join to `dim_stock`. Run `universe_refresh_job`, launch a partition of `stock_batch_refresh_job`, then run `medallion_refresh_job`. Use `dbt build --select +dim_stock+` through the provided dbt script for a full validation.

## Schedule does not run

`dagster dev` must remain running because it includes the daemon. Check that the schedule is enabled in the UI, the timezone/cron are valid, and the Windows logon task is running after restart.
