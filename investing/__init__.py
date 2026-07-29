"""Investing analysis package."""

from .data_fetch.investing_com import (
    find_stock,
    get_stock_data,
    merge_stock_histories,
    resolve_yahoo_symbol,
    search_stocks,
)
from .data_fetch.stock_universe import fetch_stock_universe
from .data_fetch.market_intelligence import fetch_financial_statements, fetch_stock_news
from .db.store import (
    init_db,
    query_financial_statement_trends,
    query_fundamental_snapshots,
    query_latest_analysis_snapshots,
    query_stock_history,
    query_stock_histories,
    query_stock_news,
    query_stock_universe,
    query_stock_universe_symbols,
    save_analysis_snapshots,
    save_fundamental_snapshot,
    save_financial_statements,
    save_news_articles,
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
from .core.ranking import (
    build_rankings,
    build_sector_fundamental_score,
    sector_profile_frame,
    top_stocks_by_country_sector,
)
from .core.portfolio import analyze_stock, analyze_stocks
from .core.watchlist import analyze_watchlist, append_watchlist_rows, read_watchlist, write_watchlist
from .core.stock_analyzer import compute_stock_metrics, build_scorecard
from .core.stock_analysis import (
    altman_z_zone,
    calculate_altman_z_score,
    compute_dividend_history_metrics,
    merge_fundamentals,
)

__all__ = [
    "find_stock",
    "get_stock_data",
    "merge_stock_histories",
    "resolve_yahoo_symbol",
    "search_stocks",
    "fetch_stock_universe",
    "fetch_financial_statements",
    "fetch_stock_news",
    "init_db",
    "save_stock_history",
    "save_fundamental_snapshot",
    "save_financial_statements",
    "save_news_articles",
    "save_analysis_snapshots",
    "save_stock_universe",
    "query_stock_history",
    "query_stock_histories",
    "query_stock_news",
    "query_financial_statement_trends",
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
    "build_sector_fundamental_score",
    "sector_profile_frame",
    "top_stocks_by_country_sector",
    "compute_stock_metrics",
    "build_scorecard",
    "calculate_altman_z_score",
    "altman_z_zone",
    "merge_fundamentals",
    "compute_dividend_history_metrics",
]
