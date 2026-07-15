import argparse
from typing import Sequence

from investing.core.html_report import generate_watchlist_report
from investing.core.portfolio import analyze_stocks
from investing.core.watchlist import analyze_watchlist, read_watchlist
from investing.data_fetch.investing_com import search_stocks
from investing.data_fetch.stock_universe import fetch_stock_universe
from investing.db.duckdb_store import (
    init_db,
    query_stock_universe,
    save_fundamental_snapshot,
    save_stock_history,
    save_stock_universe,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch, analyze, and store stock data using Investing.com and DuckDB."
    )
    parser.add_argument(
        "--symbols",
        "-s",
        help="Comma-separated symbols or names to analyze (e.g. EQNR,ORK)",
    )
    parser.add_argument(
        "--search",
        "-q",
        help="Search term to list matching stocks for a given country",
    )
    parser.add_argument(
        "--watchlist",
        "-w",
        nargs="?",
        const="watchlist.csv",
        help="Use a watchlist CSV file to analyze stocks. Default: watchlist.csv",
    )
    parser.add_argument(
        "--html-output",
        help="Write an HTML watchlist report to this path",
    )
    parser.add_argument(
        "--country",
        default="norway",
        help="Country to search or analyze stocks for (default: norway)",
    )
    parser.add_argument(
        "--countries",
        help="Comma-separated countries for stock universe refresh/selection. Defaults to --country.",
    )
    parser.add_argument(
        "--markets",
        help="Comma-separated market names or MICs to filter stock universe rows (e.g. XOSL,MERK).",
    )
    parser.add_argument(
        "--refresh-universe",
        action="store_true",
        help="Fetch and replace stock universe rows in DuckDB for the selected countries.",
    )
    parser.add_argument(
        "--list-universe",
        action="store_true",
        help="List stocks from the DuckDB stock universe table.",
    )
    parser.add_argument(
        "--from-universe",
        action="store_true",
        help="Analyze stocks selected from the DuckDB stock universe table.",
    )
    parser.add_argument(
        "--universe-source",
        choices=["auto", "euronext", "investpy"],
        default="auto",
        help="Source used by --refresh-universe. Auto uses Euronext for Norway and investpy otherwise.",
    )
    parser.add_argument(
        "--data-source",
        choices=["auto", "investing", "yahoo"],
        default="auto",
        help="Historical/fundamental data source for analysis. Auto tries Investing.com then Yahoo Finance.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1825,
        help="Number of historical days to fetch for each stock (default: 1825 for 5 years)",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.01,
        help="Minimum Sharpe-style score to recommend a stock",
    )
    parser.add_argument(
        "--max-volatility",
        type=float,
        default=0.06,
        help="Maximum acceptable volatility for recommendation",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save historical data to DuckDB",
    )
    return parser.parse_args()


def split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def selected_countries(args: argparse.Namespace) -> list[str]:
    return split_csv(args.countries) or split_csv(args.country) or ["norway"]


def print_search_results(matches: Sequence[object]) -> None:
    if not matches:
        print("No matching stocks found.")
        return

    print(f"Found {len(matches)} results:")
    for match in matches:
        symbol = getattr(match, "symbol", "?")
        name = getattr(match, "name", "?")
        exchange = getattr(match, "exchange", "?")
        country = getattr(match, "country", "?")
        print(f"- {symbol} | {name} | {exchange} | {country}")


def print_universe_rows(rows) -> None:
    if rows.empty:
        print("No stock universe rows found.")
        return

    print(f"Found {len(rows)} stock universe rows:")
    for row in rows.itertuples(index=False):
        market = row.exchange_mic or row.market or row.exchange
        print(f"- {row.symbol} | {row.yahoo_symbol} | {row.name} | {row.country} | {market} | {row.isin} | {row.source}")


def analyze_universe_rows(
    rows,
    days: int,
    min_score: float,
    max_volatility: float,
    data_source: str,
) -> list[dict]:
    results: list[dict] = []
    for row in rows.itertuples(index=False):
        analyzed = analyze_stocks(
            [row.symbol],
            country=row.country,
            days=days,
            min_score=min_score,
            max_volatility=max_volatility,
            data_source=data_source,
        )
        if analyzed:
            result = analyzed[0]
            if not result.get("name") or result.get("name") == row.symbol:
                result["name"] = row.name
            if not result.get("exchange"):
                result["exchange"] = row.exchange_mic or row.market or row.exchange
            result["universe_market"] = row.market
            result["universe_isin"] = row.isin
            result["yahoo_symbol"] = row.yahoo_symbol
            results.append(result)
    return results


def main() -> None:
    args = parse_args()

    if args.search:
        matches = search_stocks(args.search, country=args.country)
        print_search_results(matches)
        return

    init_db()
    results = []
    countries = selected_countries(args)
    symbol_filters = split_csv(args.symbols)
    market_filters = split_csv(args.markets)

    if args.refresh_universe:
        universe = fetch_stock_universe(countries=countries, source=args.universe_source)
        saved_count = save_stock_universe(universe, replace_countries=countries)
        source_summary = ", ".join(sorted(universe["source"].dropna().unique())) if not universe.empty else "n/a"
        print(f"Saved {saved_count} stock universe rows for {', '.join(countries)} (source: {source_summary}).")

    if args.list_universe:
        rows = query_stock_universe(
            countries=countries,
            symbols=symbol_filters,
            markets=market_filters,
        )
        print_universe_rows(rows)
        if not args.from_universe:
            return

    if args.watchlist is not None:
        watchlist_path = args.watchlist
        watchlist = read_watchlist(watchlist_path)
        if not watchlist:
            raise SystemExit(f"Watchlist file is empty or not found: {watchlist_path}")
        results = analyze_watchlist(
            watchlist,
            days=args.days,
            min_score=args.min_score,
            max_volatility=args.max_volatility,
            data_source=args.data_source,
        )
    elif args.from_universe:
        universe_rows = query_stock_universe(
            countries=countries,
            symbols=symbol_filters,
            markets=market_filters,
        )
        if universe_rows.empty:
            raise SystemExit("No matching stock universe rows found. Run --refresh-universe first or adjust filters.")
        results = analyze_universe_rows(
            universe_rows,
            days=args.days,
            min_score=args.min_score,
            max_volatility=args.max_volatility,
            data_source=args.data_source,
        )
    else:
        if args.refresh_universe:
            return

        if not args.symbols:
            raise SystemExit("Please provide --symbols to analyze, --watchlist for a watchlist file, or --search to list matches.")

        symbols = symbol_filters
        if not symbols:
            raise SystemExit("No valid symbols were provided.")

        results = analyze_stocks(
            symbols,
            country=args.country,
            days=args.days,
            min_score=args.min_score,
            max_volatility=args.max_volatility,
            data_source=args.data_source,
        )

    if args.html_output:
        output_path = generate_watchlist_report(results, args.html_output)
        print(f"Generated HTML report: {output_path}")

    for result in results:
        symbol = result.get("symbol")
        if result.get("error"):
            print(f"\n{symbol}: ERROR - {result['error']}")
            continue

        print(f"\n{symbol} ({result.get('name', '')})")
        print(f" Country: {result.get('country', '')} | Exchange: {result.get('exchange', '')}")
        print(f" Data source: {result.get('data_source', args.data_source)} | Yahoo: {result.get('yahoo_symbol', '')}")
        scorecard = result.get("scorecard", {})
        print(f" Recommended: {scorecard.get('recommended')} | Reason: {scorecard.get('reason')}")
        print(f" Score: {scorecard.get('score', 0.0):.4f} | Volatility: {scorecard.get('volatility', 0.0):.4f}")
        print(f" Price change: {scorecard.get('price_change', 0.0):.2%} | Latest close: {scorecard.get('latest_close', 0.0)}")

        technical = result.get("technical", {})
        print(f" Technical direction: {technical.get('direction', 'n/a')} | Signal: {technical.get('signal_summary', 'n/a')}")
        fundamentals = result.get("fundamentals", {})
        if fundamentals:
            print(
                f" Fundamental P/E: {fundamentals.get('pe_ratio', 'n/a')} | "
                f"EPS: {fundamentals.get('eps', 'n/a')} | "
                f"Dividend yield: {fundamentals.get('dividend_yield', 'n/a')} | "
                f"Altman Z: {fundamentals.get('altman_z_score', 'n/a')} "
                f"({fundamentals.get('altman_z_zone', 'Unavailable')})"
            )

        if args.save and not result.get("error"):
            save_stock_history(
                result["data"],
                ticker=result["symbol"],
                name=result["name"],
                country=result["country"],
                exchange=result["exchange"],
                data_source=result.get("data_source", args.data_source),
            )
            save_fundamental_snapshot(
                result.get("fundamentals", {}),
                ticker=result["symbol"],
                name=result["name"],
                country=result["country"],
                exchange=result["exchange"],
                data_source=result.get("data_source", args.data_source),
            )
            print(" Saved historical and fundamental data to DuckDB")


if __name__ == "__main__":
    main()
