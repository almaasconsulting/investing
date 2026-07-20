# Architecture

## Runtime flow

```text
Yahoo Finance ----\
                   > Python ingestion -> PostgreSQL landing tables
Investing.com ----/                         |
                                             v
                                      dbt Bronze tables
                                             |
                                             v
                                      dbt Silver tables
                                             |
                                             v
                                dbt Gold dimensions and facts
                                      |                 |
                                      v                 v
                                  Streamlit         SQL/BI tools

Dagster orchestrates independent universe, partitioned ingestion, and dbt jobs
```

## Landing and Bronze

The Python write API owns PostgreSQL's configured landing-schema tables. Writes are append-oriented and include `ingested_at`, source names, field-source JSON, complete provider-payload JSON for fundamentals, and provider-specific OHLCV columns for prices.

The daily universe contains all Norwegian equities from the Oslo Bors, Euronext Growth Oslo, and Euronext Expand Oslo markets. Other countries are membership-based: S&P 500, S&P/TSX 60, and the configured European flagship indexes, with additional US/Canadian REIT and dividend-aristocrat collections. A required catalog failure occurs before replacement, preventing a partial response from erasing a valid country universe; optional US/Canadian enrichments emit warnings and retain the required index constituents.

dbt copies new landing rows into physical tables in the `bronze` schema. Bronze is the durable source-shaped layer used for replay and audit. It deliberately performs almost no business cleanup.

## Silver

The `silver` schema contains cleaned types and identifiers, normalized countries/symbols, and one current record per business key. Overlap rows are ranked by `ingested_at`; the newest provider result wins. Standard price columns already implement the provider rule: Yahoo first, Investing.com only for gaps. The raw `yahoo_*` and `investing_*` columns remain alongside them.

## Gold

The `gold` schema is analysis-ready and uses conformed keys:

- `dim_stock`: one stock per country and symbol.
- `dim_sector`: normalized sector values.
- `dim_date`: trading-date attributes.
- `fact_stock_price_daily`: OHLCV, technical indicators, and source audit fields.
- `fact_fundamental_snapshot`: point-in-time valuation, quality, dividend, growth, leverage, and Altman Z-score values.
- `fact_analysis_snapshot`: historical analysis runs and extracted headline scores.
- `fact_latest_stock_analysis`: latest analysis per stock.
- `fact_sector_summary`: sector/date aggregate benchmarks.

Market intelligence follows the same path. The append-oriented `news_article_landing` and `financial_statement_landing` tables retain provider records. Silver deduplicates news and retains the latest revision from each statement provider. Gold selects Yahoo per normalized metric/period when available, with Investing.com filling missing values. Gold exposes `dim_news_article`, `bridge_stock_news`, `fact_stock_news`, `fact_financial_statement`, and `fact_fundamental_trend` to Stock View. Article bodies are not copied into the analytics database; only metadata, summaries, and links are stored.

## Incremental strategy

For each stock, ingestion reads the latest landing date and requests only the missing interval plus `INVESTING_INCREMENTAL_OVERLAP_DAYS`. The overlap captures provider corrections and late observations. Silver removes duplicates using the latest ingestion timestamp. Fundamental APIs generally expose current snapshots rather than a date range, so the latest snapshot is fetched per analysis run; an unchanged snapshot hash is not appended twice on the same date.

`INVESTING_FULL_REFRESH=true` makes ingestion request the configured analysis history again. `scripts/run_dbt.ps1 -FullRefresh` independently rebuilds all dbt relations. These are maintenance controls, not normal daily settings.

News and statements use stable hashes: unchanged records are skipped, while corrections become new Bronze revisions. `INVESTING_CONTENT_SCOPE` controls whether scheduled content ingestion covers the watchlist or full universe independently of price analysis.

## Partitioned batches and fairness

Each country/symbol identity is assigned to one of 50 stable Dagster partitions with SHA-256. A schedule runs every 15 minutes and selects the partition containing the globally least-recently attempted eligible stock. A successful analysis makes that stock ineligible for automated analysis for 24 hours; only an explicit manual `force_update` launch bypasses this rule. Inside that partition, each ingestion asset takes up to 200 rows by default, ordered `last_attempted_at NULLS FIRST`. Both successes and failures update `stock_update_status`, which gives the full universe round-robin fairness and makes retries automatic. Existing analysis/news/statement timestamps seed the queue when upgrading an older database.

The partition count and batch size are configurable. Changing the partition count remaps stocks, so do that only as a deliberate operational change; it does not duplicate Bronze records because landing writes remain hash/deduplication based.

## Concurrency

PostgreSQL handles concurrent readers and writers with transaction isolation. Dagster, dbt, and Streamlit connect to the same server, so Streamlit observes committed rows while ingestion continues. The Dagster run queue remains limited to one by default to control external-provider load.

Provider calls inside each asset use a bounded thread pool (`INVESTING_FETCH_WORKERS`, default 4). Database connections are short-lived, and provider requests run concurrently before ordered persistence. Keep all updates inside the provided pipeline functions.
