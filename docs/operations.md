# Operations

## Normal daily operation

Dagster uses three independent jobs:

1. `universe_refresh_job` refreshes all Norwegian Oslo-market stocks and discovers companies from Investing.com's US, Canadian, and selected European index catalogs. Stable major-index, REIT, and dividend sources fill gaps; overlaps are deduplicated and a failed required fallback leaves the previous universe unchanged.
2. `stock_batch_refresh_job` runs one deterministic stock partition every 15 minutes. Each asset takes up to `INVESTING_BATCH_SIZE` oldest stocks in that partition for prices/fundamentals and news/statements. Provider requests use four concurrent workers by default.
3. `medallion_refresh_job` executes the native dbt assets hourly. Dagster displays every Bronze, Silver, and Gold model separately, including lineage and dbt tests as asset checks.

Runs are observable in the Dagster UI. A failed stock is recorded in the run summary while other stock results continue; a failed dbt test fails the transformation asset.

## Manual commands

```powershell
# Start orchestration UI/daemon
.\scripts\start_dagster.ps1

# Incremental dbt build/test only (no source fetching)
.\scripts\run_dbt.ps1

# Rebuild every dbt table after a schema/model migration
.\scripts\run_dbt.ps1 -FullRefresh

# Start analysis UI
.\scripts\start_streamlit.ps1

# Rebuild local HTML documentation
.\.venv\Scripts\python.exe -m mkdocs build --clean
```

## In-app updates

Streamlit uses the same shared ingestion/persistence service. An update started in the app therefore follows identical provider-merging rules, while PostgreSQL safely supports concurrent reads and writes.

Stock View reads cached Silver/Gold news and statement history. **Refresh selected stock** fetches only that stock and rebuilds the medallion models. Country and market selectors show checked selections. The catalog contains all Norwegian stocks plus deduplicated companies from the configured Investing.com index catalogs, with stable major-index/REIT/dividend fallbacks. A continuous schedule loops through this curated universe in retryable batches.

For a database-wide sector comparison, select the desired countries/markets, choose **Use all filtered stocks**, then click **Load Database Analysis**. Do not use **Run Analysis** for the entire database; live app analysis is capped at one batch. Build sector rankings from the saved Dagster results.

Stocks never processed are selected first, followed by the least recently attempted stocks. An automated price/analysis run only selects a stock when its last successful update is at least 24 hours old. The scheduler chooses the partition containing the globally oldest eligible work; within it, price/analysis and content maintain separate oldest-first queues. Failed attempts receive a timestamp too, so a permanently bad ticker cannot starve the queue. Dagster logs live progress every ten stocks by default. Set `INVESTING_PROGRESS_EVERY=1` to log every stock.

To rerun specific work, open `stock_batch_refresh_job`, choose a partition such as `batch_017`, and launch it. A partition is a stable hash bucket, not one fixed batch: repeated runs take the next oldest stocks from that bucket. To sweep several buckets, use Dagster's partition backfill UI. Jobs are queued one at a time by default to limit provider load.

The 24-hour guard remains enabled for an ordinary manual launch. To deliberately
override it, add this run configuration in Dagster Launchpad:

```yaml
ops:
  bronze_incremental_market_data:
    config:
      force_update: true
```

Scheduled runs always use the default `false` value.

## Full refresh

Use full refresh only if history is missing/corrupt or a model schema change cannot be migrated incrementally:

1. Stop the three schedules or ensure no run is active.
2. Back up PostgreSQL with `pg_dump`.
3. Set `$env:INVESTING_FULL_REFRESH='true'` only for the source re-fetch run.
4. Run the Dagster job.
5. Reset the value to `false`.
6. Run `scripts\run_dbt.ps1 -FullRefresh` when physical dbt schemas must also be recreated.

## Updating software

Pull changes while services are stopped, then rerun the installer against the same DataRoot. It reuses `.venv` and the database, upgrades requirements, runs dbt, rebuilds docs, and tests the installation.

## Documentation automation

Markdown under `docs/` is authoritative. A push to `main` triggers `.github/workflows/documentation.yml`, builds `site/`, uploads the HTML artifact, and deploys GitHub Pages. In repository Settings, set **Pages > Build and deployment > Source** to **GitHub Actions** once.
