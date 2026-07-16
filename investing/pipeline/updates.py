from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from filelock import FileLock

from investing.core.portfolio import analyze_stocks
from investing.core.watchlist import analyze_watchlist, read_watchlist
from investing.data_fetch.stock_universe import fetch_stock_universe
from investing.db.duckdb_store import (
    save_analysis_snapshots,
    save_fundamental_snapshot,
    save_stock_history,
    save_stock_universe,
)
from investing.pipeline.config import PipelineSettings


def _lock(settings: PipelineSettings) -> FileLock:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    return FileLock(str(settings.lock_path), timeout=settings.update_lock_timeout)


def analyze_universe_frame(
    universe: pd.DataFrame,
    *,
    days: int,
    min_score: float,
    max_volatility: float,
    data_source: str,
) -> list[dict]:
    results: list[dict] = []
    for row in universe.itertuples(index=False):
        analyzed = analyze_stocks(
            [row.symbol],
            country=row.country,
            days=days,
            min_score=min_score,
            max_volatility=max_volatility,
            data_source=data_source,
        )
        if not analyzed:
            continue
        result = analyzed[0]
        if not result.get("name") or result.get("name") == row.symbol:
            result["name"] = getattr(row, "name", row.symbol)
        if not result.get("exchange"):
            result["exchange"] = (
                getattr(row, "exchange_mic", "")
                or getattr(row, "market", "")
                or getattr(row, "exchange", "")
            )
        result["yahoo_symbol"] = getattr(row, "yahoo_symbol", "")
        result["universe_market"] = getattr(row, "market", "")
        result["universe_isin"] = getattr(row, "isin", "")
        results.append(result)
    return results


def persist_analysis_results(
    results: list[dict],
    *,
    days: int,
    min_score: float,
    max_volatility: float,
    fallback_source: str = "auto",
    run_timestamp: datetime | None = None,
    settings: PipelineSettings | None = None,
    acquire_lock: bool = True,
) -> dict[str, int]:
    settings = settings or PipelineSettings.from_env()

    def _persist() -> dict[str, int]:
        timestamp = run_timestamp or datetime.now()
        saved_history = 0
        for result in results:
            if result.get("error"):
                continue
            result.setdefault("last_run_at", timestamp)
            result["cached"] = bool(result.get("cached", False))
            data = result.get("data")
            if not isinstance(data, pd.DataFrame) or data.empty:
                continue
            save_stock_history(
                data,
                ticker=result["symbol"],
                name=result.get("name", result["symbol"]),
                country=result.get("country", "norway"),
                exchange=result.get("exchange", ""),
                data_source=result.get("data_source", fallback_source),
                db_path=settings.database_path,
            )
            save_fundamental_snapshot(
                result.get("fundamentals", {}),
                ticker=result["symbol"],
                name=result.get("name", result["symbol"]),
                country=result.get("country", "norway"),
                exchange=result.get("exchange", ""),
                data_source=result.get(
                    "fundamental_data_source",
                    result.get("data_source", fallback_source),
                ),
                db_path=settings.database_path,
            )
            saved_history += 1

        saved_snapshots = save_analysis_snapshots(
            results,
            days=days,
            min_score=min_score,
            max_volatility=max_volatility,
            run_timestamp=timestamp,
            db_path=settings.database_path,
        )
        return {"price_histories": saved_history, "analysis_snapshots": saved_snapshots}

    if not acquire_lock:
        return _persist()
    with _lock(settings):
        return _persist()


def refresh_stock_universe(settings: PipelineSettings | None = None) -> dict[str, Any]:
    settings = settings or PipelineSettings.from_env()
    with _lock(settings):
        universe = fetch_stock_universe(
            countries=settings.countries,
            source=settings.universe_source,
        )
        rows = save_stock_universe(
            universe,
            replace_countries=settings.countries,
            db_path=settings.database_path,
        )
    return {"rows": rows, "countries": list(settings.countries)}


def run_watchlist_update(settings: PipelineSettings | None = None) -> dict[str, Any]:
    settings = settings or PipelineSettings.from_env()
    with _lock(settings):
        rows = read_watchlist(settings.watchlist_path)
        results = analyze_watchlist(
            rows,
            days=settings.analysis_days,
            min_score=settings.min_score,
            max_volatility=settings.max_volatility,
            data_source=settings.data_source,
        )
        persisted = persist_analysis_results(
            results,
            days=settings.analysis_days,
            min_score=settings.min_score,
            max_volatility=settings.max_volatility,
            fallback_source=settings.data_source,
            settings=settings,
            acquire_lock=False,
        )
    errors = sum(1 for result in results if result.get("error"))
    return {
        "watchlist_rows": len(rows),
        "analyzed": len(results) - errors,
        "errors": errors,
        **persisted,
    }
