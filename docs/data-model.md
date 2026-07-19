# Data model

## Landing (`main`)

| Table | Grain | Purpose |
|---|---|---|
| `stock_universe` | stock/country refresh | Source security master. |
| `stock_history` | stock/country/date/ingestion | Append-oriented merged and provider OHLCV. |
| `fundamental_snapshot` | stock/country/date/ingestion | Point-in-time fundamentals plus provider payloads. |
| `analysis_snapshot` | stock/country/run | Calculated analysis results and errors. |
| `news_article_landing` | stock/article/provider/revision | Incremental news metadata, links, and raw payloads. |
| `financial_statement_landing` | stock/provider/period/line item/revision | Quarterly and annual provider statement history. |

## Bronze

The existing four Bronze models plus `bronze_news_article` and `bronze_financial_statement` are incremental physical copies with a `bronze_loaded_at` audit timestamp. They are the dbt-controlled raw layer.

## Silver

| Model | Grain | Refinement |
|---|---|---|
| `silver_stock_universe` | country/symbol | Normalized identifiers; latest refresh. |
| `silver_stock_price_daily` | country/ticker/date | Latest overlap correction; typed OHLCV and provenance. |
| `silver_fundamental_snapshot` | country/ticker/date | Latest daily snapshot; normalized sector/yield. |
| `silver_analysis_snapshot` | country/symbol/run | Clean analysis history and JSON payloads. |
| `silver_news_article` | country/ticker/article | Latest deduplicated article metadata. |
| `silver_financial_statement` | country/ticker/provider/period/line item | Latest revision retained independently for Yahoo and Investing.com. |

## Gold

Gold facts reference `dim_stock.stock_key`; dates use integer `YYYYMMDD` keys. Provider JSON remains available in the fundamental fact, and provider-specific OHLCV remains in the price fact so source decisions can be audited without returning to Bronze.

News and statements add `dim_news_article`, `bridge_stock_news`, `fact_stock_news`, `fact_financial_statement`, and `fact_fundamental_trend`.

dbt tests enforce unique dimension keys and prevent duplicate daily-price and fundamental fact grains. Add business-specific tests to `analytics/models/medallion.yml` or `analytics/tests/`.

`financial_statement_landing.record_hash` makes refreshes idempotent while retaining company restatements. `silver_financial_statement` normalizes line items and retains each provider's newest revision. `fact_financial_statement` applies `Yahoo -> Investing.com` independently for each metric and fiscal period. `fact_fundamental_trend` adds previous-period, period-change, and year-over-year calculations. Quarterly year-over-year compares four reported periods back; annual year-over-year compares the prior year.
