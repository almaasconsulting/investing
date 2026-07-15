# Investing Analysis Project

Initial modular Python setup to fetch stock data from Investing.com, store it in DuckDB, and run simple analysis.

## Structure

- `investing/data_fetch/investing_com.py` - fetches stock data from Investing.com via `investpy` and Yahoo Finance via `yfinance`
- `investing/data_fetch/stock_universe.py` - fetches country stock universes, with Euronext Oslo as the preferred Norway source
- `investing/db/duckdb_store.py` - stores and queries historical stock data in DuckDB
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

The UI defaults market data to Yahoo Finance. Use **Refresh Universe** once, then filter markets/stocks and run analysis or clustering.

From the UI you can also:

- add selected universe stocks to `watchlist.csv`
- add a manual symbol to `watchlist.csv`
- edit and save the watchlist table
- run analysis from the saved watchlist
- automatically save selected-stock analysis snapshots to DuckDB and reload the latest saved analysis after app restart
- inspect a selected analyzed stock with price, moving averages, technical fields, and fundamentals
- search the selectable universe by ticker, Yahoo ticker, company name, or ISIN
- select stocks directly or select saved sectors to analyze whole sector groups
- filter analyzed stocks by technical and fundamental criteria such as direction, score, volatility, RSI, P/E, dividend yield, growth, ROE, debt/equity, and Altman Z-score
- compare filtered stocks in a spider chart across normalized technical and fundamental dimensions
- rank analyzed stocks by a blended technical/fundamental score
- group rankings by correlation cluster, market, country, sector, industry, trend, recommendation, valuation, dividend bucket, or Altman Z-score zone
- view the CLI-style printed output in the Analysis tab
- view the generated HTML report inside the Analysis tab
- view numeric UI tables rounded to 3 decimals

## Notes

- This scaffold is designed to support any country or exchange, with Norway as the first example.
- Use `investpy` to search and fetch stock data by symbol/name.
- DuckDB will store historical records in `data/investing.duckdb`.
- The database now stores:
  - 5-year share price history
  - daily technical indicator values such as MA20, MA50, MA200, RSI14, direction, and signal summary
  - data source provenance for saved history and fundamentals
  - fundamental snapshots including market cap, P/E ratio, EPS, dividend yield, beta, revenue, Altman Z-score, and more
  - analysis snapshots with last run timestamp, scorecard, technical overview, fundamentals, and metrics
- The watchlist is configured in `watchlist.csv` at the repository root.
- Altman Z-score uses the original public-company model and Yahoo's latest annual statements. It is primarily intended for publicly traded manufacturers; missing inputs are shown as unavailable rather than estimated.
- A country-aware `stock_universe` table stores selectable stock metadata for clustering and portfolio construction, including Yahoo Finance tickers.

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

The CLI can analyze multiple symbols at once and optionally save the results to DuckDB.

## Stock Universe

Refresh the Norwegian stock universe into DuckDB:

```powershell
python main.py --refresh-universe --country norway
```

Norway refreshes use Euronext's Oslo product directory by default, covering Oslo Bors, Euronext Growth Oslo, and Euronext Expand Oslo. If the live source is unavailable, `--universe-source auto` falls back to `investpy`'s packaged stock list.

List all Norwegian rows now stored in DuckDB:

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
