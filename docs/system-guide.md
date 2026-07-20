# Complete system guide

This guide explains the platform as one connected system. It is intended for installation, development, operation, troubleshooting, and future extension. Use the focused [storage-computer setup](storage-computer-setup.md), [operations](operations.md), and [production reset](production-reset-runbook.md) guides when carrying out those procedures.

## 1. What the system does

The platform maintains a reusable stock-analysis database independently of the Streamlit application. Dagster schedules ingestion, Python obtains source data and calculates analysis snapshots, PostgreSQL provides concurrent durable storage, dbt refines the data through Bronze, Silver, and Gold, and Streamlit reads the resulting database for interactive analysis.

The main design objective is that opening the application should not require downloading and recalculating the complete universe. Automated jobs update old or missing stocks in the background. The application can still refresh one selected stock when an immediate update is needed.

<pre class="mermaid">
flowchart LR
    YF[Yahoo Finance] --> PY[Python ingestion and analysis]
    IC[Investing.com] --> PY
    IX[Index and exchange catalogs] --> PY
    PY --> L[(PostgreSQL landing schema)]
    L --> B[dbt Bronze]
    B --> S[dbt Silver]
    S --> G[dbt Gold]
    G --> UI[Streamlit]
    G --> SQL[SQL and BI clients]
    UI -. selected-stock refresh .-> PY
    D[Dagster] -. schedules and observes .-> PY
    D -. runs and observes .-> B
</pre>

## 2. Component responsibilities

| Component | Responsibility | Starts independently? | Persistent state |
|---|---|---:|---|
| Yahoo Finance | Preferred price, fundamental, dividend, news, and statement provider when a field exists. | External service | None locally |
| Investing.com / investpy | Fills source gaps and provides catalog, price, fundamental, and statement fallbacks. | External service | None locally |
| Python package `investing` | Provider access, normalization, merging, technical calculations, rankings, queue selection, and PostgreSQL writes. | Used by Dagster and Streamlit | PostgreSQL only |
| PostgreSQL | Concurrent system of record for landing data and all medallion schemas. | Yes | Database server storage |
| Dagster | Schedules jobs, selects partitions, displays progress, retries, lineage, logs, and run history. | Yes, port `3000` | `DAGSTER_HOME` |
| dbt | Converts landing records into tested Bronze, Silver, and Gold models. | Invoked by Dagster or script | PostgreSQL schemas and `analytics/target` artifacts |
| Streamlit | Interactive universe filtering, stock view, analysis, rankings, charts, and selected-stock refresh. | Yes, normally port `8501` | Session state plus PostgreSQL |
| MkDocs | Builds this Markdown documentation into static HTML. | On demand or GitHub Actions | `site/` build output |

Dagster and Streamlit are separate processes. PostgreSQL makes simultaneous committed reads and writes safe. Stopping Streamlit does not stop ingestion; stopping Dagster prevents scheduled updates but does not prevent database reads.

## 3. Repository structure

```text
investing/
|-- investing/
|   |-- core/                 calculations, analysis, ranking, clustering, watchlist
|   |-- data_fetch/           Yahoo, Investing.com, universe, news, statement adapters
|   |-- db/                   PostgreSQL store, compatibility layer, query/write API
|   |-- orchestration/        Dagster assets, jobs, schedules, dbt integration
|   `-- pipeline/             settings, incremental queues, persistence workflows
|-- analytics/
|   |-- models/
|   |   |-- bronze/           source-shaped incremental models
|   |   |-- silver/           typed, normalized, deduplicated models
|   |   `-- gold/             dimensions, facts, trends, and serving models
|   |-- macros/               PostgreSQL-safe dbt helpers
|   |-- profiles.yml          environment-driven dbt connection
|   `-- dbt_project.yml       model defaults and project configuration
|-- scripts/                  install, start, dbt, reset, and environment scripts
|-- docs/                     Markdown documentation sources
|-- tests/                    unit and regression tests
|-- streamlit_app.py          interactive application
|-- workspace.yaml            Dagster code-location configuration
|-- mkdocs.yml                documentation navigation and HTML settings
`-- requirements.txt          Python dependencies
```

## 4. Runtime topology

On the storage/analysis computer, the normal topology is:

<pre class="mermaid">
flowchart TB
    subgraph Computer[Storage and analysis computer]
        DA[Dagster webserver and daemon\nlocalhost:3000]
        ST[Streamlit\nlocalhost:8501]
        PG[(PostgreSQL\ninvesting database)]
        FS[Runtime files\n.runtime-env.ps1 and DAGSTER_HOME]
        DA --> PG
        ST --> PG
        DA --> FS
        ST --> FS
    end
    DA --> NET[External data providers]
    ST -->|only explicit selected-stock refresh| NET
</pre>

Run Dagster and Streamlit in separate PowerShell windows. Both launchers load `.runtime-env.ps1`, clear `PYTHONPATH`, disable the user site-packages directory, and invoke the interpreter inside `.venv`.

## 5. Stock-universe policy

The universe is the security master that controls which stocks enter the automated queues.

| Region | Primary policy | Fallback behavior |
|---|---|---|
| Norway | Complete Euronext Oslo stock directory: Oslo Bors, Euronext Growth Oslo, and Euronext Expand Oslo. | Yahoo Oslo discovery, then Investing.com/investpy stock metadata. |
| United States | Equity constituents discovered from the Investing.com US index catalog. | S&P 500, Nasdaq-100, Russell 2000, REIT, and dividend collections. |
| Canada | Equity constituents discovered from the Investing.com Canada index catalog. | S&P/TSX 60, S&P/TSX Composite, REIT, and dividend collections. |
| Selected European countries | Equity constituents discovered from the Investing.com European catalog, filtered to configured countries. | Configured national major indexes. |

Companies appearing in several indexes are deduplicated by country and Yahoo symbol. Indexes without resolvable company constituents are ignored. A blocked optional catalog produces a Dagster warning and uses stable fallbacks; it must not replace a valid country universe with an empty result.

The default configured countries are Norway, United States, Canada, United Kingdom, France, Germany, Switzerland, Sweden, Netherlands, Italy, Spain, Denmark, and Finland.

## 6. Provider merging and provenance

`INVESTING_DATA_SOURCE=auto` means both providers may be queried. The merge rule is applied per field rather than per stock:

1. Use the Yahoo value when it exists and is valid.
2. Otherwise use the Investing.com value.
3. If only one provider succeeds, continue with that provider.
4. Preserve provider-specific values and field-source metadata for audit.

For price history, merged `open`, `high`, `low`, `close`, and `volume` coexist with `yahoo_*` and `investing_*` columns. For fundamentals, `field_sources_json` identifies field-level decisions and `provider_payloads_json` retains source payloads. JSON serialization converts non-finite numeric values such as `NaN` and infinity to JSON `null`, because PostgreSQL JSON parsing rejects them.

Statements apply the same priority independently for every line item and fiscal period. Yahoo is selected when that specific metric-period value exists; otherwise Investing.com is selected. This prevents an incomplete Yahoo statement from hiding available Investing.com history.

## 7. Ingestion and analysis flow

<pre class="mermaid">
sequenceDiagram
    participant D as Dagster
    participant Q as Oldest-first queue
    participant P as Providers
    participant A as Analyzer
    participant L as PostgreSQL landing
    participant T as dbt
    participant U as Streamlit

    D->>Q: Choose oldest eligible partition
    Q-->>D: Up to INVESTING_BATCH_SIZE stocks
    D->>P: Fetch prices and fundamentals
    P-->>A: Yahoo and/or Investing.com data
    A->>A: Merge, technicals, scores, Z-score
    A->>L: Commit history, fundamentals, analysis, status
    D->>P: Fetch news and statements
    P->>L: Commit content landing rows and status
    D->>T: Scheduled dbt build
    T->>L: Read landing and publish Bronze/Silver/Gold
    U->>L: Read committed Silver/Gold results
</pre>

An individual provider or ticker error is recorded for that stock while the batch continues. Progress logs show completed stocks, percentage, elapsed time, estimated remaining time, rows written, and sampled errors.

## 8. PostgreSQL schemas and layers

The configured landing schema defaults to `main`. dbt creates `bronze`, `silver`, and `gold` schemas.

| Layer | Owner | Design rule | Typical consumer |
|---|---|---|---|
| Landing (`main`) | Python | Append or upsert source/application records with audit metadata. | Bronze dbt models and operational queue queries |
| Bronze | dbt | Durable, source-shaped incremental copies; minimal transformation. | Silver models, replay, audit |
| Silver | dbt | Typed, normalized, provider-aware, deduplicated business grains. | Gold models and detailed investigation |
| Gold | dbt | Conformed dimensions, facts, latest-state and trend tables. | Streamlit, rankings, SQL, BI |

### 8.1 Landing tables

| Table | Grain or key | Important contents | Written by |
|---|---|---|---|
| `stock_universe` | country + symbol per refresh | Yahoo symbol, company, market, MIC, ISIN, currency, source URL, active flag | Universe refresh |
| `stock_history` | country + ticker + date + ingestion | Merged OHLCV, raw provider OHLCV, MA20/50/200, RSI14, direction, signals | Price/analysis batch |
| `fundamental_snapshot` | country + ticker + snapshot + ingestion | Valuation, profitability, leverage, growth, dividend history, REIT FFO, Altman Z-score, provenance JSON | Price/analysis batch |
| `analysis_snapshot` | country + symbol + run timestamp | Scorecard, technical, fundamentals and metrics JSON, filters, errors | Analyzer and Streamlit save action |
| `news_article_landing` | stock + article + provider/revision | Publication metadata, summary, URL, payload and record hash | Market-intelligence batch |
| `financial_statement_landing` | stock + provider + statement + period + line item/revision | Quarterly/annual line items, values, currency, reported/fetched times, payload | Market-intelligence batch |
| `stock_update_status` | update type + country + ticker | Last attempted, last succeeded, and last error | All incremental workflows |

`stock_update_status` is operational state rather than a dbt source. It controls fairness, retries, and eligibility.

### 8.2 Bronze models

| Model | Landing source | Incremental unique key |
|---|---|---|
| `bronze_stock_universe` | `stock_universe` | country + symbol |
| `bronze_stock_history` | `stock_history` | country + ticker + date + ingested time |
| `bronze_fundamental_snapshot` | `fundamental_snapshot` | country + ticker + snapshot date + ingested time |
| `bronze_analysis_snapshot` | `analysis_snapshot` | country + symbol + run timestamp |
| `bronze_news_article` | `news_article_landing` | record hash |
| `bronze_financial_statement` | `financial_statement_landing` | record hash |

### 8.3 Silver models

| Model | Grain | Refinement |
|---|---|---|
| `silver_stock_universe` | country + symbol | Normalized identifiers and latest valid membership. |
| `silver_stock_price_daily` | country + ticker + date | Latest correction, typed OHLCV, retained provider provenance. |
| `silver_fundamental_snapshot` | country + ticker + snapshot date | Latest daily snapshot and normalized ratios, sector and yield. |
| `silver_analysis_snapshot` | country + symbol + run timestamp | Clean analysis history and sanitized JSON. |
| `silver_news_article` | country + ticker + article | Latest deduplicated article metadata. |
| `silver_financial_statement` | country + ticker + provider + period + line item | Latest provider revision retained independently. |

### 8.4 Gold models

| Model | Type and grain | Purpose |
|---|---|---|
| `dim_stock` | Dimension; one country/symbol | Conformed stock key plus current descriptive attributes. |
| `dim_sector` | Dimension; one sector | Sector grouping for ranking and summaries. |
| `dim_date` | Dimension; one date | Integer `YYYYMMDD` date key. |
| `dim_news_article` | Dimension; one article | Reusable article attributes. |
| `fact_stock_price_daily` | Fact; stock/date | Analysis-ready daily prices, indicators, and source fields. |
| `fact_fundamental_snapshot` | Fact; stock/snapshot date | Analysis-ready point-in-time fundamentals and dividend fields. |
| `fact_analysis_snapshot` | Fact; stock/run | Historical calculated results and JSON payloads. |
| `fact_latest_stock_analysis` | Serving table; one stock | Latest saved analysis for database-wide Streamlit loading. |
| `fact_sector_summary` | Aggregate; sector | Sector-level fundamental summary. |
| `fact_stock_news` | Fact; stock/article | Stock-specific article facts. |
| `bridge_stock_news` | Bridge; stock/article | Many-to-many stock-to-article relationship. |
| `fact_financial_statement` | Fact; stock/period/line item | Yahoo-preferred, Investing-fallback financial statements. |
| `fact_fundamental_trend` | Trend; stock/period/line item | Previous-period and year-over-year comparisons. |

The current project contains thirteen Gold models; the Gold layer is intentionally broader than a minimal star schema because it also contains latest-state and trend serving tables.

<pre class="mermaid">
erDiagram
    DIM_STOCK ||--o{ FACT_STOCK_PRICE_DAILY : stock_key
    DIM_DATE ||--o{ FACT_STOCK_PRICE_DAILY : date_key
    DIM_STOCK ||--o{ FACT_FUNDAMENTAL_SNAPSHOT : stock_key
    DIM_STOCK ||--o{ FACT_ANALYSIS_SNAPSHOT : stock_key
    DIM_STOCK ||--o{ FACT_FINANCIAL_STATEMENT : stock_key
    DIM_STOCK ||--o{ FACT_FUNDAMENTAL_TREND : stock_key
    DIM_STOCK ||--o{ BRIDGE_STOCK_NEWS : stock_key
    DIM_NEWS_ARTICLE ||--o{ BRIDGE_STOCK_NEWS : article_key
    DIM_SECTOR ||--o{ FACT_SECTOR_SUMMARY : sector_key
</pre>

## 9. Dagster orchestration

Dagster exposes Python ingestion assets and every dbt model as a first-class asset. The custom dbt translator groups models by `bronze`, `silver`, and `gold` folder and attaches ingestion dependencies to Bronze models.

| Job | Assets | Default schedule | Purpose |
|---|---|---|---|
| `universe_refresh_job` | `bronze_stock_universe` Python asset | Daily at `03:00` Europe/Oslo | Refresh active stock membership. |
| `stock_batch_refresh_job` | `bronze_incremental_market_data`, then `bronze_market_intelligence` | Every 15 minutes | Update one selected partition of prices, fundamentals, analysis, news, and statements. |
| `medallion_refresh_job` | All native dbt assets and tests | 10 minutes past each hour | Publish and validate Bronze, Silver, and Gold. |

### Partitions and oldest-first selection

Stocks are assigned to one of 50 stable hash partitions by default. A partition is a durable bucket, not a fixed one-time batch. At each scheduled run:

1. Inspect eligible work across partitions.
2. Select the partition containing the globally oldest work.
3. Within that partition, select up to `INVESTING_BATCH_SIZE` stocks.
4. Prioritize stocks never attempted, then the oldest attempted stocks.
5. Stamp failed attempts so one permanently failing ticker cannot starve the queue.
6. Skip a recently successful stock until the normal 24-hour guard allows it again.

Price/fundamental and news/statement queues maintain separate update types. They can therefore progress independently even though the two assets execute sequentially inside a partition to control provider load.

Use `force_update: true` only for a deliberate manual rerun. It bypasses the normal freshness guard and increases provider traffic.

## 10. Incremental behavior

| Area | Incremental method | Full rebuild needed when |
|---|---|---|
| Universe | Replace membership only after required source validation. | Policy or identifier semantics change materially. |
| Daily prices | Request dates after the latest stored date with a seven-day correction overlap. | Historical corruption or incompatible schema change. |
| Fundamentals | Add point-in-time snapshots and deduplicate downstream. | Normally never. |
| Analysis | Save timestamped snapshots; latest Gold model selects newest. | Scoring semantics require historical recalculation. |
| News | Hash and deduplicate articles/revisions. | Normally never. |
| Statements | Hash provider revisions and retain period history. | Line-item normalization changes substantially. |
| dbt | `delete+insert` incremental keys for most models. | Grain/key/model logic changes incompatibly. |

The overlap window handles late corrections without downloading five years for every daily run. `INVESTING_FULL_REFRESH=true` and dbt `--full-refresh` are recovery tools, not normal scheduling settings.

## 11. Analysis and ranking

The analyzer calculates technical indicators and fundamental fields before saving the snapshot. Important outputs include:

- moving averages, RSI, return, volatility, direction and signal summary;
- valuation, growth, margins, return on equity/assets, leverage and liquidity;
- dividend yield, years paid, consecutive years, five-year CAGR and payout ratio;
- REIT-specific funds from operations and FFO yield when available;
- Altman Z-score and its distress/grey/safe zone when sufficient statement inputs exist;
- sector-aware fundamental score, technical score, blended ranking, and coverage.

Sector-specific scoring changes indicator weights because a useful leverage, payout, valuation, or FFO level depends on the business model. Missing fields do not become zero-quality values; they contribute neutral handling while coverage reports how much evidence was available. Altman Z-score is primarily meaningful for publicly traded manufacturers and should not be treated as a universal bankruptcy prediction.

## 12. Streamlit application

| Tab | Reads | Important actions | Network/provider behavior |
|---|---|---|---|
| Universe | Stock universe | Filter countries/markets/stocks, refresh universe, add to watchlist | Universe refresh contacts catalog providers. |
| Watchlist | CSV watchlist and database | Edit/save watchlist, run a bounded watchlist analysis | Analysis can fetch selected stocks. |
| Stock View | Gold/Silver history, news, statements | Inspect one stock; refresh selected stock | Refresh contacts providers only for that stock. |
| Analysis | Latest saved analysis or bounded live selection | Load Database Analysis, Run Analysis, save snapshots | Database load is read-only; live run fetches selected stocks. |
| Spider | Loaded analysis | Compare normalized dimensions | Read-only after analysis is loaded. |
| Rankings | Loaded saved/live analysis | Build sector-aware rankings and grouping | Computes from loaded results; it does not rerun Dagster. |
| Clusters | Stored price history | Build return-correlation clusters | Reads prices and computes locally. |

For a whole-universe view, use **Load Database Analysis** after Dagster has populated results. Do not use **Run Analysis** for thousands of stocks; live analysis is intentionally bounded. **Build Rankings** calculates ranking output from the analysis currently loaded in the Streamlit session. It does not wait for or trigger the scheduled Dagster job.

Percent-like fields such as dividend yield, margins, growth, ROE, payout ratio, return, and volatility should be displayed as percentages while remaining numeric ratios in storage unless a model explicitly normalizes them.

## 13. Configuration reference

The installer writes `.runtime-env.ps1`. Treat it as a secret because it contains the database password. It is ignored by Git.

### Database and paths

| Variable | Default | Meaning |
|---|---|---|
| `INVESTING_DATABASE_URL` | Constructed | Advanced PostgreSQL URL override. |
| `INVESTING_POSTGRES_HOST` | `localhost` | PostgreSQL server. |
| `INVESTING_POSTGRES_PORT` | `5432` | PostgreSQL port. |
| `INVESTING_POSTGRES_DATABASE` | `investing` | Database name. |
| `INVESTING_POSTGRES_USER` | `investing` | Application login. |
| `INVESTING_POSTGRES_PASSWORD` | empty/prompted | Application password. |
| `INVESTING_POSTGRES_SSLMODE` | `prefer` | psycopg SSL mode. |
| `INVESTING_POSTGRES_SCHEMA` | `main` | Python landing schema. |
| `INVESTING_WATCHLIST_PATH` | repository/default | Persistent watchlist CSV. |
| `DAGSTER_HOME` | data root or `.dagster` | Dagster metadata, logs and run storage. |

### Universe, ingestion, and analysis

| Variable | Default | Operational effect |
|---|---:|---|
| `INVESTING_COUNTRIES` | 13 configured countries | Comma-separated universe countries. |
| `INVESTING_UNIVERSE_SOURCE` | `index` | Universe policy selector. |
| `INVESTING_DATA_SOURCE` | `auto` | `auto`, Yahoo, or Investing provider policy. |
| `INVESTING_ANALYSIS_DAYS` | `1825` | Requested analysis lookback in days. |
| `INVESTING_INCREMENTAL_OVERLAP_DAYS` | `7` | Price correction overlap. |
| `INVESTING_ANALYSIS_SCOPE` | `universe` | Automated analysis scope: universe or watchlist. |
| `INVESTING_CONTENT_SCOPE` | `universe` | News/statement scope: universe or watchlist. |
| `INVESTING_MAX_STOCKS` | unset | Optional global analysis cap. |
| `INVESTING_CONTENT_MAX_STOCKS` | unset | Optional global content cap. |
| `INVESTING_BATCH_SIZE` | `200` | Maximum selected stocks in one partition run. |
| `INVESTING_BATCH_PARTITION_COUNT` | `50` | Stable hash partition count; changing it remaps all stocks. |
| `INVESTING_FETCH_WORKERS` | `4` | Provider concurrency, constrained to 1-16. |
| `INVESTING_NEWS_COUNT` | `30` | Requested news count per stock. |
| `INVESTING_PROGRESS_EVERY` | `10` | Log every N completed stocks. |
| `INVESTING_MIN_SCORE` | `0.01` | Default analysis score threshold. |
| `INVESTING_MAX_VOLATILITY` | `0.06` | Default analysis volatility threshold. |
| `INVESTING_FULL_REFRESH` | `false` | Python full-refresh override; normally off. |

### Schedules and dbt

| Variable | Default | Meaning |
|---|---|---|
| `INVESTING_UNIVERSE_CRON` | `0 3 * * *` | Daily universe cron. |
| `INVESTING_BATCH_CRON` | `*/15 * * * *` | Partitioned ingestion cron. |
| `INVESTING_DBT_CRON` | `10 * * * *` | Medallion dbt cron. |
| `INVESTING_TIMEZONE` | `Europe/Oslo` | Dagster schedule timezone. |
| `INVESTING_DBT_EXECUTABLE` | `.venv` dbt executable | Optional dbt executable override. |

After changing schedule, partition-count, database, or Dagster variables, restart Dagster so definitions and daemon state are reloaded. Streamlit must be restarted after changing its runtime environment.

## 14. Installation and startup

From the repository root on a new Windows computer:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_storage_computer.ps1 `
  -DataRoot C:\repo\InvestingData `
  -InstallPostgreSQL
```

Start the services in separate PowerShell windows:

```powershell
.\scripts\start_dagster.ps1
```

```powershell
.\scripts\start_streamlit.ps1
```

Open Dagster at <http://localhost:3000> and Streamlit at <http://localhost:8501>. See [Storage computer setup](storage-computer-setup.md) for parameters, PostgreSQL provisioning, startup tasks, and verification.

Install or repair all dependencies with the environment interpreter, not a global `pip`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Verify a package such as `html5lib` is inside the environment:

```powershell
.\.venv\Scripts\python.exe -c "import html5lib; print(html5lib.__version__); print(html5lib.__file__)"
```

The path must contain `.venv\Lib\site-packages`.

## 15. Normal operating procedure

1. Leave PostgreSQL running.
2. Leave `start_dagster.ps1` running so the webserver and daemon can launch schedules.
3. Confirm the three schedules are enabled in Dagster Automation.
4. Run `universe_refresh_job` after changing universe code or starting with an empty database.
5. Let `stock_batch_refresh_job` cycle through oldest partitions.
6. Let `medallion_refresh_job` publish dbt results hourly, or run it manually after initial ingestion.
7. Start Streamlit whenever interactive access is needed; it does not need to remain open for ingestion.
8. Use Dagster event logs to investigate provider warnings and per-stock failures.

The first useful empty-database sequence is:

```text
universe_refresh_job
        |
        v
one or more stock_batch_refresh_job partitions
        |
        v
medallion_refresh_job
        |
        v
Load Database Analysis in Streamlit
```

## 16. Concurrency, transactions, and availability

PostgreSQL replaced file-based DuckDB because Dagster writes while Streamlit reads. Each operation uses short-lived connections and transactions. Readers see committed state and do not lock out the long-running ingestion process as a single-process database file could.

Be aware of these boundaries:

- A stock can be viewed while another stock or the same stock is being updated; the UI sees the last committed version until the new transaction commits.
- dbt models are updated transactionally by PostgreSQL, but dependent models become current as their dbt steps finish.
- Streamlit session data does not automatically become a new database query unless the app reruns or its cache expires/clears.
- Do not run multiple uncontrolled Dagster daemons against the same `DAGSTER_HOME`; they can launch duplicate scheduled work.
- Increasing batch size or worker count raises provider traffic, memory use, run duration, and rate-limit risk.

## 17. Failure and recovery matrix

| Symptom | Likely boundary | What is preserved | First response |
|---|---|---|---|
| Investing.com catalog returns 403 | External provider/catalog | Existing universe plus stable fallbacks | Review warnings; do not wipe data. Retry later. |
| One ticker fails | Provider or symbol mapping | Other batch stocks and previous ticker data | Inspect `stock_update_status`; allow oldest-first retry. |
| dbt model fails | Transformation/data type | Landing and previously committed models | Read dbt stdout/log; fix model/data, rerun medallion job. |
| Streamlit shows old values | App cache/session or dbt not yet run | Database remains valid | Rerun/refresh app; confirm latest dbt job succeeded. |
| Dagster schedule does not launch | Daemon, toggle, cron, timezone | Database remains readable | Keep `dagster dev` running and inspect Automation. |
| Import comes from global Python | `PYTHONPATH` or wrong executable | Data unaffected | Use `.venv` interpreter and remove external `PYTHONPATH`. |
| PostgreSQL connection fails | Service, credentials, firewall, `pg_hba.conf` | On-disk database remains | Load runtime env, test dbt debug/psycopg connection. |
| Gold tables are empty | Missing upstream sequence | Landing may contain data | Run universe, batch ingestion, then medallion build. |

Do not delete `C:\repo\InvestingData` or drop PostgreSQL schemas as a first troubleshooting step. Use the [production reset runbook](production-reset-runbook.md) only when a deliberate clean rebuild is required.

## 18. Change-impact map

| If you change... | Also inspect or run... |
|---|---|
| Provider field mapping | Landing DDL, Bronze/Silver columns, Gold facts, Streamlit formatting, tests |
| Universe source or symbol normalization | `stock_universe`, `dim_stock`, partition mapping, Yahoo-symbol resolution |
| A landing-table grain | Bronze unique key, Silver deduplication, Gold joins, dbt tests |
| Ranking fields or weights | Fundamental extraction, saved snapshots, ranking UI, documentation |
| A dbt model name/path | Dagster manifest, group/lineage, downstream `ref()` calls, docs |
| PostgreSQL schema or credentials | `.runtime-env.ps1`, dbt profile, Dagster and Streamlit restart |
| Partition count | All stocks remap; restart Dagster and avoid mixing old/new partition assumptions |
| Batch size/workers | Provider rate limits, run duration, schedule overlap, machine capacity |
| Documentation | `mkdocs.yml` navigation if new page; strict MkDocs build |

## 19. Security and maintenance

- Never commit `.runtime-env.ps1`, database passwords, provider tokens, or PostgreSQL dumps.
- Use a dedicated PostgreSQL application role and restrict remote access with firewall and `pg_hba.conf` rules.
- Back up PostgreSQL independently of `DAGSTER_HOME`; Dagster metadata is not the analytical database.
- Back up the persistent watchlist and any manually maintained configuration.
- Apply dependency updates in `.venv`, run tests and `dbt build`, then deploy the same revision to production.
- Review source terms, rate limits, and robots/access behavior before increasing automated requests.

## 20. Documentation lifecycle

Markdown files under `docs/` are authoritative. Build locally with:

```powershell
.\.venv\Scripts\python.exe -m mkdocs build --strict --clean
```

The output is written to `site/`. When documentation is pushed to `main`, `.github/workflows/documentation.yml` runs a strict build and deploys the HTML to GitHub Pages. A strict build failure prevents publication, which catches missing pages and malformed internal links.

## 21. Related guides

- [Storage computer setup](storage-computer-setup.md)
- [Production clean reset](production-reset-runbook.md)
- [PostgreSQL configuration](postgresql.md)
- [Operations](operations.md)
- [Data model](data-model.md)
- [Troubleshooting](troubleshooting.md)

