# Investing Medallion Platform

This application collects stock-universe, daily-price, fundamental, and analysis data from Yahoo Finance and Investing.com. Dagster schedules and observes updates, dbt transforms the data through Bronze, Silver, and Gold, PostgreSQL stores it, and Streamlit provides interactive analysis.

Read the [complete system guide](system-guide.md) for the connected architecture, data model, orchestration, configuration, operating procedures, diagrams, and change-impact reference.

For vendor-neutral dbt exam preparation, use the
[dbt Analytics Engineering Certification guide](dbt-analytics-engineering-certification.md).
It follows the current exam domains and includes concept maps, comparison tables,
hands-on labs, practice questions, a six-week study plan, and the progression toward
the dbt Architect certification.

## Start here

On a new Windows storage/analysis computer, clone this repository, open PowerShell in the repository root, and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_storage_computer.ps1 `
  -DataRoot C:\repo\InvestingData `
  -InstallPostgreSQL
```

Then start the two applications in separate PowerShell windows:

```powershell
.\scripts\start_dagster.ps1
.\scripts\start_streamlit.ps1
```

- Dagster: <http://localhost:3000>
- Streamlit: <http://localhost:8501>

Dagster enables daily universe refresh, 15-minute partitioned ingestion, and hourly dbt publishing by default. Stocks that have never run are processed first, then the oldest attempted stocks across the full configured universe.

## Documentation formats

The files in `docs/` are the Markdown documentation. `python -m mkdocs build` creates the HTML edition in `site/`. The main-branch documentation workflow rebuilds and publishes that HTML edition to GitHub Pages automatically.

## Important behavior

- The default scope is every active stock in the configured country universe. Set `INVESTING_ANALYSIS_SCOPE=watchlist` for a smaller run.
- The daily universe contains all Norwegian Oslo-market stocks and deduplicated Investing.com index constituents for the configured US, Canadian, and European markets, with stable major-index/REIT/dividend fallbacks.
- Price ingestion is incremental. It requests only dates after the last stored date plus a configurable seven-day correction overlap.
- Yahoo values win when both providers contain a field. Investing.com fills missing Yahoo values. Both raw provider values and provenance remain available.
- dbt incrementally updates Bronze, Silver, and Gold. Use a full refresh only for recovery or incompatible schema changes.
- Streamlit and Dagster use short-lived PostgreSQL connections, so analysis remains readable during ingestion.

This is an analysis and screening system, not investment advice.
