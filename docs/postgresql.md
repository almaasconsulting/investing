# PostgreSQL configuration

PostgreSQL is the runtime backend. It allows Dagster to write
while Streamlit reads committed data using normal transaction isolation.

## Connection parameters

The installer accepts separate, explicit parameters:

| Installer parameter | Runtime variable | Default |
|---|---|---|
| `-PostgresHost` | `INVESTING_POSTGRES_HOST` | `localhost` |
| `-PostgresPort` | `INVESTING_POSTGRES_PORT` | `5432` |
| `-PostgresDatabase` | `INVESTING_POSTGRES_DATABASE` | `investing` |
| `-PostgresUser` | `INVESTING_POSTGRES_USER` | `investing` |
| `-PostgresPassword` | `INVESTING_POSTGRES_PASSWORD` | prompted |
| `-PostgresSslMode` | `INVESTING_POSTGRES_SSLMODE` | `prefer` |
| `-PostgresSchema` | `INVESTING_POSTGRES_SCHEMA` | `main` |

`INVESTING_DATABASE_URL` is an optional advanced override. Leave it empty to
have the application safely construct the URL from the parameters above.

## Install on the storage computer

From `C:\repo\investing` in a normal PowerShell window:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_storage_computer.ps1 `
  -DataRoot C:\repo\InvestingData `
  -PostgresHost localhost `
  -PostgresPort 5432 `
  -PostgresDatabase investing `
  -PostgresUser investing
```

The password is requested without echoing it. Add `-InstallPostgreSQL` when
PostgreSQL or the application role/database still needs to be provisioned.

The generated `.runtime-env.ps1` contains the connection password and is
ignored by Git. Limit access to the repository directory to the service user.

## Start services

```powershell
.\scripts\start_dagster.ps1
.\scripts\start_streamlit.ps1
```

Run these in two PowerShell windows. Both launchers load the same runtime
configuration automatically.
