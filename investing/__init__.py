"""Investing analysis package."""

from .data_fetch.investing_com import find_stock, get_stock_data, resolve_yahoo_symbol, search_stocks
from .data_fetch.stock_universe import fetch_stock_universe
from .db.duckdb_store import (
    init_db,
    query_fundamental_snapshots,
    query_latest_analysis_snapshots,
    query_stock_history,
    query_stock_universe,
    query_stock_universe_symbols,
    save_analysis_snapshots,
    save_fundamental_snapshot,
    save_stock_history,
    save_stock_universe,
)
from .core.html_report import generate_watchlist_report
from .core.clustering import (
    build_close_price_matrix,
    cluster_by_correlation,
    compute_return_correlation,
    correlation_pairs,
)
from .core.ranking import build_rankings
from .core.portfolio import analyze_stock, analyze_stocks
from .core.watchlist import analyze_watchlist, append_watchlist_rows, read_watchlist, write_watchlist
from .core.stock_analyzer import compute_stock_metrics, build_scorecard

__all__ = [
    "find_stock",
    "get_stock_data",
    "resolve_yahoo_symbol",
    "search_stocks",
    "fetch_stock_universe",
    "init_db",
    "save_stock_history",
    "save_fundamental_snapshot",
    "save_analysis_snapshots",
    "save_stock_universe",
    "query_stock_history",
    "query_fundamental_snapshots",
    "query_latest_analysis_snapshots",
    "query_stock_universe",
    "query_stock_universe_symbols",
    "analyze_stock",
    "analyze_stocks",
    "analyze_watchlist",
    "append_watchlist_rows",
    "read_watchlist",
    "write_watchlist",
    "generate_watchlist_report",
    "build_close_price_matrix",
    "compute_return_correlation",
    "cluster_by_correlation",
    "correlation_pairs",
    "build_rankings",
    "compute_stock_metrics",
    "build_scorecard",
]
