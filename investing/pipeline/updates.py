from __future__ import annotations

import hashlib
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from investing.core.portfolio import analyze_stocks
from investing.core.watchlist import read_watchlist
from investing.data_fetch.stock_universe import fetch_stock_universe
from investing.data_fetch.market_intelligence import (
    fetch_financial_statements,
    fetch_stock_news,
)
from investing.db.store import (
    query_stock_history,
    query_stock_content_queue,
    query_stock_analysis_queue,
    query_stock_universe,
    save_analysis_snapshots,
    save_fundamental_snapshot,
    save_stock_history,
    save_stock_universe,
    save_financial_statements,
    save_news_articles,
    save_stock_update_status,
)
from investing.pipeline.config import PipelineSettings

PIPELINE_API_VERSION = 6
ProgressCallback = Callable[[dict[str, Any]], None]


def _lock(settings: PipelineSettings):
    return nullcontext()


def analyze_universe_frame(
    universe: pd.DataFrame,
    *,
    days: int,
    min_score: float,
    max_volatility: float,
    data_source: str,
    settings: PipelineSettings | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[dict]:
    settings = settings or PipelineSettings.from_env()
    rows = list(universe.itertuples(index=False))
    total = len(rows)
    if not rows:
        return []

    # Database reads are completed before network workers start. Workers only
    # perform provider I/O and calculations; they never open the database.
    with _lock(settings):
        histories = {
            (str(row.country).lower(), str(row.symbol).upper()): query_stock_history(
                row.symbol, country=row.country, db_path=settings.database_path
            )
            for row in rows
        }

    def fetch_one(position: int, row: Any) -> tuple[int, dict[str, Any]]:
        existing = histories[(str(row.country).lower(), str(row.symbol).upper())]
        fetch_days = days
        if not getattr(settings, "full_refresh", False) and not existing.empty:
            latest = pd.to_datetime(existing["date"], errors="coerce").max()
            if pd.notna(latest):
                missing_days = max(
                    0, (pd.Timestamp(date.today()) - latest.normalize()).days
                )
                fetch_days = max(
                    getattr(settings, "incremental_overlap_days", 7),
                    missing_days + getattr(settings, "incremental_overlap_days", 7),
                )
        analyzed = analyze_stocks(
            [row.symbol],
            country=row.country,
            days=days,
            min_score=min_score,
            max_volatility=max_volatility,
            data_source=data_source,
            yahoo_symbols={
                str(row.symbol): str(getattr(row, "yahoo_symbol", "") or "")
            },
            fetch_days=fetch_days,
            existing_history=existing,
        )
        result: dict[str, Any] = (
            analyzed[0]
            if analyzed
            else {"symbol": str(row.symbol), "error": "No analysis result returned."}
        )
        result.setdefault("symbol", str(row.symbol))
        result.setdefault("country", str(row.country))
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
        return position, result

    ordered_results: list[dict[str, Any] | None] = [None] * total
    completed = 0
    worker_count = min(settings.fetch_workers, total)
    with ThreadPoolExecutor(
        max_workers=worker_count, thread_name_prefix="stock-analysis"
    ) as executor:
        futures = {
            executor.submit(fetch_one, position, row): (position, row)
            for position, row in enumerate(rows)
        }
        for future in as_completed(futures):
            position, row = futures[future]
            try:
                _, result = future.result()
            except Exception as exc:
                result = {
                    "symbol": str(row.symbol),
                    "country": str(row.country),
                    "error": str(exc),
                }
            ordered_results[position] = result
            completed += 1
            error = str(result.get("error") or "")
            ingested_data = result.get("ingested_data")
            rows_fetched = (
                len(ingested_data)
                if isinstance(ingested_data, pd.DataFrame) and not error
                else 0
            )
            if progress_callback:
                progress_callback({
                    "index": completed, "total": total,
                    "symbol": str(row.symbol), "country": str(row.country),
                    "succeeded": not error, "error": error,
                    "rows_written": rows_fetched,
                    "price_providers": result.get("price_providers", []),
                    "fundamental_providers": result.get("fundamental_providers", []),
                })
    return [result for result in ordered_results if result is not None]


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
        saved_fundamentals = 0
        for result in results:
            error = str(result.get("error") or "")
            save_stock_update_status(
                update_type="analysis",
                ticker=str(result.get("symbol", "")),
                country=str(result.get("country", "norway")),
                succeeded=not error,
                error=error,
                db_path=settings.database_path,
            )
            if error:
                continue
            result.setdefault("last_run_at", timestamp)
            result["cached"] = bool(result.get("cached", False))
            data = result.get("ingested_data", result.get("data"))
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
            fundamental_saved = save_fundamental_snapshot(
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
            saved_fundamentals += int(fundamental_saved)
            saved_history += 1

        saved_snapshots = save_analysis_snapshots(
            results,
            days=days,
            min_score=min_score,
            max_volatility=max_volatility,
            run_timestamp=timestamp,
            db_path=settings.database_path,
        )
        return {
            "price_histories": saved_history,
            "fundamental_snapshots": saved_fundamentals,
            "analysis_snapshots": saved_snapshots,
        }

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
    return {
        "rows": rows,
        "countries": list(settings.countries),
        "warnings": list(universe.attrs.get("warnings", [])),
    }


def _batch_metadata(universe: pd.DataFrame, batch_key: str | None) -> dict[str, Any]:
    attempts = pd.Series(dtype="datetime64[ns]")
    if "last_attempted_at" in universe.columns:
        attempts = pd.to_datetime(universe["last_attempted_at"], errors="coerce").dropna()
    return {
        "batch_key": batch_key or "manual",
        "batch_rows": len(universe),
        "oldest_previous_attempt": attempts.min().isoformat() if not attempts.empty else "never",
        "newest_previous_attempt": attempts.max().isoformat() if not attempts.empty else "never",
    }


def _reserve_updates(
    universe: pd.DataFrame,
    *,
    update_type: str,
    settings: PipelineSettings,
) -> None:
    """Move selected stocks to the back of the queue before releasing the lock."""
    attempted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    for row in universe.itertuples(index=False):
        save_stock_update_status(
            update_type=update_type,
            ticker=str(row.symbol),
            country=str(getattr(row, "country", "norway")),
            succeeded=False,
            error="Update reserved; awaiting provider result.",
            attempted_at=attempted_at,
            db_path=settings.database_path,
        )


def _stock_partition(symbol: str, country: str, partition_count: int) -> int:
    identity = f"{country.lower()}|{symbol.upper()}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(identity).digest()[:8], "big") % partition_count


def _partition_queue(
    universe: pd.DataFrame,
    *,
    batch_key: str,
    partition_count: int,
    batch_size: int,
) -> pd.DataFrame:
    partition_index = int(batch_key.rsplit("_", 1)[-1])
    memberships = [
        _stock_partition(str(row.symbol), str(row.country), partition_count)
        for row in universe.itertuples(index=False)
    ]
    selected = universe[pd.Series(memberships, index=universe.index) == partition_index]
    return selected.head(batch_size).copy()


def oldest_batch_partition_key(settings: PipelineSettings | None = None) -> str:
    """Return the partition containing the globally least-recently attempted stock."""
    settings = settings or PipelineSettings.from_env()
    with _lock(settings):
        queues = [
            query_stock_analysis_queue(
                countries=settings.countries, limit=None, db_path=settings.database_path
            ),
            query_stock_content_queue(
                countries=settings.countries, limit=None, db_path=settings.database_path
            ),
        ]
    frames = [
        queue[["symbol", "country", "last_attempted_at"]]
        for queue in queues if not queue.empty
    ]
    if not frames:
        return "batch_000"
    combined = pd.concat(frames, ignore_index=True)
    combined["attempt"] = pd.to_datetime(combined["last_attempted_at"], errors="coerce")
    combined["partition"] = [
        _stock_partition(str(symbol), str(country), settings.batch_partition_count)
        for symbol, country in zip(combined["symbol"], combined["country"])
    ]
    oldest = combined.sort_values(
        ["attempt", "country", "symbol"], na_position="first"
    ).iloc[0]
    return f"batch_{int(oldest['partition']):03d}"


def run_watchlist_update(
    settings: PipelineSettings | None = None,
    *,
    limit: int | None = None,
    batch_key: str | None = None,
    force_update: bool = False,
) -> dict[str, Any]:
    settings = settings or PipelineSettings.from_env()
    with _lock(settings):
        rows = read_watchlist(settings.watchlist_path)
        universe = pd.DataFrame(rows)
        if not force_update and not universe.empty:
            eligible = query_stock_analysis_queue(
                countries=sorted(universe["country"].astype(str).str.lower().unique()),
                limit=None,
                minimum_success_age_hours=24.0,
                db_path=settings.database_path,
            )
            eligible_keys = {
                (str(row.country).lower(), str(row.symbol).upper())
                for row in eligible.itertuples(index=False)
            }
            universe = universe[
                [
                    (str(row.get("country", "norway")).lower(), str(row.get("symbol", "")).upper())
                    in eligible_keys
                    for row in universe.to_dict("records")
                ]
            ].copy()
        if limit is not None:
            universe = universe.head(limit)
        for column in ("name", "exchange", "yahoo_symbol", "market", "isin"):
            if column not in universe.columns:
                universe[column] = ""
        _reserve_updates(universe, update_type="analysis", settings=settings)
    results = analyze_universe_frame(
        universe,
        days=settings.analysis_days,
        min_score=settings.min_score,
        max_volatility=settings.max_volatility,
        data_source=settings.data_source,
        settings=settings,
    )
    notes = {
        (str(row.get("symbol", "")).upper(), str(row.get("country", "norway")).lower()): row.get("notes", "")
        for row in rows
    }
    for result in results:
        result["notes"] = notes.get(
            (
                str(result.get("symbol", "")).upper(),
                str(result.get("country", "norway")).lower(),
            ),
            "",
        )
    persisted = persist_analysis_results(
        results,
        days=settings.analysis_days,
        min_score=settings.min_score,
        max_volatility=settings.max_volatility,
        fallback_source=settings.data_source,
        settings=settings,
    )
    errors = sum(1 for result in results if result.get("error"))
    return {
        "watchlist_rows": len(rows),
        "analyzed": len(results) - errors,
        "errors": errors,
        "fetch_workers": settings.fetch_workers,
        **_batch_metadata(universe, batch_key),
        **persisted,
    }


def run_universe_update(
    settings: PipelineSettings | None = None,
    *,
    limit: int | None = None,
    batch_key: str | None = None,
    partition_count: int | None = None,
    progress_callback: ProgressCallback | None = None,
    force_update: bool = False,
) -> dict[str, Any]:
    """Incrementally analyze every active stock in the configured universe."""
    settings = settings or PipelineSettings.from_env()
    with _lock(settings):
        universe = query_stock_analysis_queue(
            countries=settings.countries,
            limit=None if batch_key else (
                limit if limit is not None else settings.max_stocks
            ),
            minimum_success_age_hours=None if force_update else 24.0,
            db_path=settings.database_path,
        )
        if batch_key:
            universe = _partition_queue(
                universe,
                batch_key=batch_key,
                partition_count=partition_count or settings.batch_partition_count,
                batch_size=limit or settings.batch_size,
            )
        _reserve_updates(universe, update_type="analysis", settings=settings)
    results = analyze_universe_frame(
        universe,
        days=settings.analysis_days,
        min_score=settings.min_score,
        max_volatility=settings.max_volatility,
        data_source=settings.data_source,
        settings=settings,
        progress_callback=progress_callback,
    )
    persisted = persist_analysis_results(
        results,
        days=settings.analysis_days,
        min_score=settings.min_score,
        max_volatility=settings.max_volatility,
        fallback_source=settings.data_source,
        settings=settings,
    )
    errors = sum(1 for result in results if result.get("error"))
    return {
        "universe_rows": len(universe),
        "analyzed": len(results) - errors,
        "errors": errors,
        "fetch_workers": settings.fetch_workers,
        **_batch_metadata(universe, batch_key),
        **persisted,
    }


def run_configured_analysis_update(
    settings: PipelineSettings | None = None,
    progress_callback: ProgressCallback | None = None,
    force_update: bool = False,
) -> dict[str, Any]:
    settings = settings or PipelineSettings.from_env()
    if settings.analysis_scope == "watchlist":
        return run_watchlist_update(settings, force_update=force_update)
    if settings.analysis_scope != "universe":
        raise ValueError("INVESTING_ANALYSIS_SCOPE must be 'universe' or 'watchlist'.")
    return run_universe_update(
        settings, progress_callback=progress_callback, force_update=force_update
    )


def run_configured_analysis_batch(
    *,
    batch_size: int,
    batch_key: str,
    partition_count: int,
    settings: PipelineSettings | None = None,
    progress_callback: ProgressCallback | None = None,
    force_update: bool = False,
) -> dict[str, Any]:
    settings = settings or PipelineSettings.from_env()
    if settings.analysis_scope == "watchlist":
        return run_watchlist_update(
            settings, limit=batch_size, batch_key=batch_key,
            force_update=force_update,
        )
    if settings.analysis_scope != "universe":
        raise ValueError("INVESTING_ANALYSIS_SCOPE must be 'universe' or 'watchlist'.")
    return run_universe_update(
        settings,
        limit=batch_size,
        batch_key=batch_key,
        partition_count=partition_count,
        progress_callback=progress_callback,
        force_update=force_update,
    )


def _fetch_stock_intelligence(
    symbol: str,
    country: str,
    *,
    yahoo_symbol: str = "",
    currency: str = "",
    settings: PipelineSettings,
) -> dict[str, Any]:
    """Fetch provider content without opening a database connection."""
    errors: list[str] = []
    news = pd.DataFrame()
    statements = pd.DataFrame()
    try:
        news = fetch_stock_news(
            symbol, country, yahoo_symbol=yahoo_symbol, count=settings.news_count
        )
    except Exception as exc:
        errors.append(f"news: {exc}")
    try:
        statements = fetch_financial_statements(
            symbol,
            country,
            yahoo_symbol=yahoo_symbol,
            currency=currency,
            source=settings.data_source,
        )
    except Exception as exc:
        errors.append(f"statements: {exc}")
    return {
        "symbol": symbol,
        "country": country,
        "news": news,
        "statements": statements,
        "errors": errors,
    }


def _persist_stock_intelligence(
    result: dict[str, Any], settings: PipelineSettings
) -> dict[str, Any]:
    errors = list(result.get("errors") or [])
    news_rows = save_news_articles(
        result.get("news", pd.DataFrame()), db_path=settings.database_path
    )
    statement_rows = save_financial_statements(
        result.get("statements", pd.DataFrame()), db_path=settings.database_path
    )
    save_stock_update_status(
        update_type="content",
        ticker=str(result["symbol"]),
        country=str(result["country"]),
        succeeded=not errors,
        error="; ".join(errors),
        db_path=settings.database_path,
    )
    return {
        "symbol": result["symbol"], "country": result["country"],
        "news_rows": news_rows, "statement_rows": statement_rows,
        "errors": errors,
    }


def refresh_stock_intelligence(
    symbol: str,
    country: str,
    *,
    yahoo_symbol: str = "",
    currency: str = "",
    settings: PipelineSettings | None = None,
    acquire_lock: bool = True,
) -> dict[str, Any]:
    """Fetch content without a lock, then persist it through one writer."""
    settings = settings or PipelineSettings.from_env()
    fetched = _fetch_stock_intelligence(
        symbol, country, yahoo_symbol=yahoo_symbol, currency=currency,
        settings=settings,
    )

    if not acquire_lock:
        return _persist_stock_intelligence(fetched, settings)
    with _lock(settings):
        return _persist_stock_intelligence(fetched, settings)


def run_market_intelligence_update(
    settings: PipelineSettings | None = None,
    *,
    limit: int | None = None,
    batch_key: str | None = None,
    partition_count: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Update news/statements for the configured watchlist or capped universe."""
    settings = settings or PipelineSettings.from_env()
    with _lock(settings):
        if settings.content_scope == "watchlist":
            rows = read_watchlist(settings.watchlist_path)
            universe = pd.DataFrame(rows)
            if not universe.empty:
                metadata = query_stock_universe(active_only=True, db_path=settings.database_path)
                universe["_symbol"] = universe["symbol"].astype(str).str.upper()
                universe["_country"] = universe["country"].astype(str).str.lower()
                metadata["_symbol"] = metadata["symbol"].astype(str).str.upper()
                metadata["_country"] = metadata["country"].astype(str).str.lower()
                universe = universe.merge(
                    metadata[["_symbol", "_country", "yahoo_symbol", "currency"]],
                    on=["_symbol", "_country"], how="left",
                )
            effective_limit = limit if limit is not None else settings.content_max_stocks
            if effective_limit is not None:
                universe = universe.head(effective_limit)
        elif settings.content_scope == "universe":
            universe = query_stock_content_queue(
                countries=settings.countries,
                limit=None if batch_key else (
                    limit if limit is not None else settings.content_max_stocks
                ),
                db_path=settings.database_path,
            )
            if batch_key:
                universe = _partition_queue(
                    universe,
                    batch_key=batch_key,
                    partition_count=partition_count or settings.batch_partition_count,
                    batch_size=limit or settings.batch_size,
                )
        else:
            raise ValueError("INVESTING_CONTENT_SCOPE must be 'universe' or 'watchlist'.")
        _reserve_updates(universe, update_type="content", settings=settings)

    rows = list(universe.itertuples(index=False))
    total = len(rows)
    ordered_results: list[dict[str, Any] | None] = [None] * total
    completed = 0
    if rows:
        with ThreadPoolExecutor(
            max_workers=min(settings.fetch_workers, total),
            thread_name_prefix="stock-content",
        ) as executor:
            futures = {
                executor.submit(
                    _fetch_stock_intelligence,
                    str(row.symbol),
                    str(getattr(row, "country", "norway")),
                    yahoo_symbol=str(getattr(row, "yahoo_symbol", "") or ""),
                    currency=str(getattr(row, "currency", "") or ""),
                    settings=settings,
                ): (position, row)
                for position, row in enumerate(rows)
            }
            for future in as_completed(futures):
                position, row = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "symbol": str(row.symbol),
                        "country": str(getattr(row, "country", "norway")),
                        "news": pd.DataFrame(), "statements": pd.DataFrame(),
                        "errors": [str(exc)],
                    }
                ordered_results[position] = result
                completed += 1
                rows_fetched = sum(
                    len(result.get(name, pd.DataFrame()))
                    for name in ("news", "statements")
                    if isinstance(result.get(name), pd.DataFrame)
                )
                if progress_callback:
                    progress_callback({
                        "index": completed, "total": total,
                        "symbol": str(row.symbol),
                        "country": str(getattr(row, "country", "norway")),
                        "succeeded": not result["errors"],
                        "error": "; ".join(result["errors"]),
                        "rows_written": rows_fetched,
                    })

    fetched_results = [result for result in ordered_results if result is not None]
    totals = {"stocks": 0, "news_rows": 0, "statement_rows": 0, "errors": 0}
    with _lock(settings):
        for fetched in fetched_results:
            persisted = _persist_stock_intelligence(fetched, settings)
            totals["stocks"] += 1
            totals["news_rows"] += persisted["news_rows"]
            totals["statement_rows"] += persisted["statement_rows"]
            totals["errors"] += len(persisted["errors"])
    return {
        **totals,
        "fetch_workers": settings.fetch_workers,
        **_batch_metadata(universe, batch_key),
    }


def build_medallion(
    settings: PipelineSettings | None = None,
    *,
    full_refresh: bool = False,
    select: str | list[str] | None = None,
    acquire_lock: bool = True,
) -> dict[str, Any]:
    """Run dbt Silver/Gold transformations for CLI or in-app updates."""
    settings = settings or PipelineSettings.from_env()

    def _build() -> dict[str, Any]:
        try:
            from dbt.cli.main import dbtRunner
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "dbt is not installed. Run scripts\\install_storage_computer.ps1."
            ) from exc
        project_dir = Path(__file__).resolve().parents[2] / "analytics"
        args = [
            "build",
            "--project-dir",
            str(project_dir),
            "--profiles-dir",
            str(project_dir),
        ]
        if full_refresh:
            args.append("--full-refresh")
        if select:
            args.extend(["--select", *(select if isinstance(select, list) else [select])])
        result = dbtRunner().invoke(args)
        if not result.success:
            raise RuntimeError("dbt build failed; inspect the dbt output above.")
        return {
            "success": True,
            "project_dir": str(project_dir),
            "database": "postgresql",
        }

    if not acquire_lock:
        return _build()
    with _lock(settings):
        return _build()
