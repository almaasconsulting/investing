# Investing Analysis Project

A Dagster-orchestrated, dbt-transformed stock analysis platform using a PostgreSQL Bronze/Silver/Gold medallion architecture and a Streamlit UI.

PostgreSQL connection parameters can be configured through the installer or environment variables; see the
[storage-computer setup guide](docs/storage-computer-setup.md#configuration).

## Storage computer quick start

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_storage_computer.ps1 `
  -DataRoot C:\repo\InvestingData `
  -InstallPostgreSQL
.\scripts\start_dagster.ps1
```

Open Dagster at `http://localhost:3000`. Start the app separately with `scripts\start_streamlit.ps1`. See [the full setup guide](docs/storage-computer-setup.md), [architecture](docs/architecture.md), and [operations guide](docs/operations.md).

By default, Dagster refreshes the universe daily, processes up to 200 of the globally oldest stocks from one of 50 stable partitions every 15 minutes, and publishes Bronze/Silver/Gold with dbt hourly. Failed stocks rotate to the back of the queue and are retried on later passes.

Markdown under `docs/` is the documentation source. MkDocs builds the HTML edition into `site/`, and `.github/workflows/documentation.yml` republishes it to GitHub Pages whenever documentation changes are pushed to `main`.

## Structure

- `investing/data_fetch/investing_com.py` - fetches stock data from Investing.com via `investpy` and Yahoo Finance via `yfinance`
- `investing/data_fetch/index_universe.py` - discovers constituents from Investing.com's US, Canadian, and European index catalogs, with stable major-index/REIT/dividend fallbacks
- `investing/db/store.py` - PostgreSQL storage facade
- `investing/core/clustering.py` - builds return correlations and simple correlation clusters
- `investing/core/stock_analyzer.py` - calculates simple metrics and scores
- `main.py` - example entrypoint for running a single stock fetch and analysis
- `streamlit_app.py` - browser UI for universe selection, Yahoo analysis, and clustering

## Setup

1. Activate the virtual environment:
   - PowerShell: `.\.venv\Scripts\Activate.ps1`
   - Bash: `source .venv/Scripts/activate`
2. Install dependencies:
   - `python -m pip install -r requirements.txt`

## Run the example

```powershell
python main.py
```

## Run the UI

Start the Streamlit app:

```powershell
python -m streamlit run streamlit_app.py
```

Then open the local URL printed by Streamlit, usually:

```text
http://localhost:8501
```

The UI defaults market data to merged **auto** mode. Use **Refresh Universe** once, then filter markets/stocks and run analysis or clustering.

Choose **auto** to query Yahoo Finance and Investing.com together. Auto mode prefers Yahoo for every overlapping fundamental field and daily OHLCV value, uses Investing.com only to fill Yahoo gaps, and continues with either provider if the other fails. Provider provenance is retained in the analysis result and saved data-source fields.

From the UI you can also:

- add selected universe stocks to `watchlist.csv`
- add a manual symbol to `watchlist.csv`
- edit and save the watchlist table
- run analysis from the saved watchlist
- automatically save selected-stock analysis snapshots and reload the latest saved analysis after app restart
- inspect a selected analyzed stock with price, moving averages, technical fields, and fundamentals
- inspect cached stock news and refresh news for one selected stock
- compare quarterly and annual statements with period and year-over-year changes
- search the selectable universe by ticker, Yahoo ticker, company name, or ISIN
- select stocks directly or select saved sectors to analyze whole sector groups
- filter analyzed stocks by technical and fundamental criteria such as direction, score, volatility, RSI, P/E, dividend yield, growth, ROE, debt/equity, and Altman Z-score
- compare filtered stocks in a spider chart across normalized technical and fundamental dimensions
- rank analyzed stocks by a blended technical/sector-specific fundamental score
- group rankings by correlation cluster, market, country, sector, industry, trend, recommendation, valuation, dividend bucket, or Altman Z-score zone
- view the CLI-style printed output in the Analysis tab
- view the generated HTML report inside the Analysis tab
- view numeric UI tables rounded to 3 decimals

## Notes

- The installed catalog includes every Norwegian stock from the Oslo markets and deduplicated constituents from Investing.com's US, Canadian, and selected European index catalogs. Configured major indexes plus US/Canadian REIT and dividend collections provide stable fallbacks.
- Use `investpy` to search and fetch stock data by symbol/name.
- PostgreSQL stores all production and application records.
- The database now stores:
  - 5-year share price history
  - daily technical indicator values such as MA20, MA50, MA200, RSI14, direction, and signal summary
  - data source provenance for saved history and fundamentals
  - fundamental snapshots including market cap, P/E ratio, EPS, dividend yield, beta, revenue, Altman Z-score, and more
  - analysis snapshots with last run timestamp, scorecard, technical overview, fundamentals, and metrics
- The watchlist is configured in `watchlist.csv` at the repository root.
- Altman Z-score uses the original public-company model and Yahoo's latest annual statements. It is primarily intended for publicly traded manufacturers; missing inputs are shown as unavailable rather than estimated.
- A country-aware `stock_universe` table stores selectable stock metadata for clustering and portfolio construction, including Yahoo Finance tickers.

## Sector-specific fundamental rankings

The ranking engine maps Yahoo sector names to the 11-sector GICS-style structure and changes the fundamental weights by sector. The default ranking view groups stocks by sector and uses 35% technical / 65% fundamental weighting. Missing indicators contribute a neutral score, while `fundamental_coverage` reports how much of the sector profile had usable data.

| Sector | Highest-weight indicators |
|---|---|
| Basic Materials | EV/EBITDA, free-cash-flow yield, debt/equity |
| Communication Services | EV/EBITDA, free-cash-flow yield, revenue growth, operating margin |
| Consumer Cyclical | P/E, earnings growth, operating margin |
| Consumer Defensive | P/E, free-cash-flow yield, dividend yield, operating margin |
| Energy | EV/EBITDA, free-cash-flow yield, debt/equity, dividend yield |
| Financial Services | ROE, ROA, price/book, P/E |
| Healthcare | Revenue growth, earnings growth, free-cash-flow yield, operating margin |
| Industrials | Free-cash-flow yield, debt/equity, ROE |
| Real Estate | FFO yield, dividend yield, EV/EBITDA, debt/equity |
| Technology | Revenue growth, earnings growth, free-cash-flow yield, operating margin |
| Utilities | Dividend yield, EV/EBITDA, debt/equity |

These profiles are transparent screening heuristics rather than investment advice or a fitted prediction model. The complete weights are visible in the Streamlit Rankings tab and in `SECTOR_FUNDAMENTAL_PROFILES` in `investing/core/ranking.py`. FFO data is not available for every Yahoo instrument; unavailable values remain neutral and reduce coverage.

The profile design is informed by S&P's GICS sector framework, NYU Stern's industry datasets for valuation, margins, returns and leverage, FDIC bank performance ratios, and Nareit's FFO guidance for real estate companies.

Dividend quality is included in every sector at a sector-dependent weight (5% for Technology and Healthcare up to 20% for Real Estate and Utilities). Its score combines sector-relative yield (35%), consecutive years paid (35%), five-year dividend CAGR (20%), and payout sustainability (10%). A yield above the normal band is penalized rather than automatically rewarded. Auto mode merges Yahoo and Investing.com dividend histories, with Yahoo preferred where both provide the same history metric.

## Watchlist and HTML report

Run the default CSV watchlist and write a report:

```powershell
python main.py --watchlist --html-output reports/watchlist_report.html
```

Run a single symbol analysis and export HTML:

```powershell
python main.py --symbols EQNR --html-output reports/watchlist_report.html
```

The HTML report includes:

- a watchlist summary table
- technical overview with moving average signals, RSI, and trend direction
- foundational KPI fields such as P/E ratio, EPS, dividend yield, market cap, and beta

## CLI Usage

Search for matching stocks:

```powershell
python main.py --search "eqnr" --country norway
```

Analyze one or more stocks:

```powershell
python main.py --symbols EQNR,ORK --country norway --days 180 --save
```

Force Yahoo Finance for price history and fundamentals:

```powershell
python main.py --symbols EQNR,ORK --country norway --data-source yahoo --days 180 --save
```

The CLI can analyze multiple symbols at once and optionally save the results to PostgreSQL.

## Stock Universe

The default catalog includes all stocks on the Oslo Bors, Euronext Growth Oslo, and Euronext Expand Oslo markets. Required index sources cover S&P 500, Nasdaq-100, Russell 2000, S&P/TSX 60, S&P/TSX Composite, FTSE 100, FTSE 250, CAC 40, CAC Next 20, DAX 40, MDAX, SMI, OMX Stockholm 30, AEX, FTSE MIB, IBEX 35, OMX Copenhagen 25, and OMX Helsinki 25. Investing.com index catalogs add further resolvable component lists for the selected countries. US and Canadian REITs and dividend aristocrats are added and all overlaps are deduplicated. Dagster refreshes the catalog daily and processes it in retryable oldest-first batches.

Refresh configured index membership into PostgreSQL:

```powershell
python main.py --refresh-universe --country norway --universe-source index
```

Norway refreshes prefer Euronext's complete official Oslo product directory, with Yahoo and Investing.com fallbacks. A failed required catalog download aborts the refresh before existing membership is replaced.

List all Norwegian rows now stored in PostgreSQL:

```powershell
python main.py --list-universe --country norway
```

List only the main Oslo Bors market using its MIC:

```powershell
python main.py --list-universe --country norway --markets XOSL
```

Analyze a selected universe slice:

```powershell
python main.py --from-universe --country norway --markets XOSL --symbols EQNR,ORK --days 365 --save
```

Analyze a universe slice using Yahoo Finance:

```powershell
python main.py --from-universe --country norway --markets XOSL --data-source yahoo --days 365 --save
```

These same country, market, and symbol filters are the intended input surface for a clustering step: select rows from `stock_universe`, use `yahoo_symbol` for direct yfinance calls when desired, fetch or reuse price history, then cluster on return correlation or distance.
