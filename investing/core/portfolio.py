from __future__ import annotations

from typing import Iterable, Mapping

import pandas as pd

from investing.core.stock_analyzer import build_scorecard, compute_stock_metrics
from investing.core.stock_analysis import add_technical_indicators, compute_technical_overview, get_stock_fundamentals
from investing.data_fetch.investing_com import (
    find_stock,
    get_stock_data,
    resolve_yahoo_symbol,
)

PORTFOLIO_API_VERSION = 3


def analyze_stock(
    symbol: str,
    country: str = "norway",
    days: int = 1825,
    min_score: float = 0.01,
    max_volatility: float = 0.06,
    data_source: str = "auto",
    yahoo_symbol: str = "",
    fetch_days: int | None = None,
    existing_history: pd.DataFrame | None = None,
) -> dict:
    data_source = data_source.strip().lower()
    yahoo_symbol = yahoo_symbol.strip() or resolve_yahoo_symbol(symbol, country)
    raw_df = get_stock_data(
        symbol,
        country=country,
        days=fetch_days if fetch_days is not None else days,
        source=data_source,
        yahoo_symbol=yahoo_symbol,
    )
    effective_price_source = raw_df.attrs.get("data_source", data_source)
    price_providers = raw_df.attrs.get("providers_used", [effective_price_source])
    fetched_dates = set(pd.to_datetime(raw_df["date"]).dt.normalize())
    if existing_history is not None and not existing_history.empty:
        raw_columns = list(
            dict.fromkeys(
                [
                    "date", "open", "high", "low", "close", "volume",
                    "price_source", "yahoo_open", "yahoo_high", "yahoo_low",
                    "yahoo_close", "yahoo_volume", "investing_open",
                    "investing_high", "investing_low", "investing_close",
                    "investing_volume",
                ]
            )
        )
        history = existing_history[
            [column for column in raw_columns if column in existing_history.columns]
        ].copy()
        fresh = raw_df[[column for column in raw_columns if column in raw_df.columns]].copy()
        raw_df = pd.concat([history, fresh], ignore_index=True, sort=False)
        raw_df["date"] = pd.to_datetime(raw_df["date"])
        raw_df = raw_df.sort_values("date").drop_duplicates("date", keep="last")
        cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=days)
        raw_df = raw_df[raw_df["date"] >= cutoff]
    df = add_technical_indicators(raw_df)
    ingested_df = df[pd.to_datetime(df["date"]).dt.normalize().isin(fetched_dates)].copy()
    metrics = compute_stock_metrics(df)
    scorecard = build_scorecard(metrics, min_score=min_score, max_volatility=max_volatility)
    technical = compute_technical_overview(df)
    fundamentals = get_stock_fundamentals(
        symbol,
        country=country,
        source=data_source,
        yahoo_symbol=yahoo_symbol,
    )
    fundamental_providers = fundamentals.get("providers_used", [])

    name = symbol
    exchange = ""
    try:
        stock = find_stock(symbol, country)
        if stock is not None:
            name = stock.name
            exchange = getattr(stock, "exchange", "")
    except Exception:
        pass

    return {
        "symbol": symbol,
        "yahoo_symbol": yahoo_symbol,
        "name": name,
        "country": country,
        "exchange": exchange,
        "data_source": effective_price_source,
        "requested_data_source": data_source,
        "price_providers": price_providers,
        "fundamental_providers": fundamental_providers,
        "fundamental_data_source": "+".join(fundamental_providers) or data_source,
        "data": df,
        "ingested_data": ingested_df,
        "metrics": metrics,
        "scorecard": scorecard,
        "technical": technical,
        "fundamentals": fundamentals,
    }


def analyze_stocks(
    symbols: Iterable[str],
    country: str = "norway",
    days: int = 180,
    min_score: float = 0.01,
    max_volatility: float = 0.06,
    data_source: str = "auto",
    yahoo_symbols: Mapping[str, str] | None = None,
    fetch_days: int | None = None,
    existing_history: pd.DataFrame | None = None,
) -> list[dict]:
    results: list[dict] = []
    yahoo_symbols = {
        str(key).upper(): str(value or "").strip()
        for key, value in (yahoo_symbols or {}).items()
    }
    for symbol in symbols:
        try:
            result = analyze_stock(
                symbol,
                country=country,
                days=days,
                min_score=min_score,
                max_volatility=max_volatility,
                data_source=data_source,
                yahoo_symbol=yahoo_symbols.get(str(symbol).upper(), ""),
                fetch_days=fetch_days,
                existing_history=existing_history,
            )
            results.append(result)
        except Exception as exc:
            results.append({"symbol": symbol, "error": str(exc)})
    return results
