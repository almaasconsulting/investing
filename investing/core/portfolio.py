from __future__ import annotations

from typing import Iterable

from investing.core.stock_analyzer import build_scorecard, compute_stock_metrics
from investing.core.stock_analysis import add_technical_indicators, compute_technical_overview, get_stock_fundamentals
from investing.data_fetch.investing_com import find_stock, get_stock_data


def analyze_stock(
    symbol: str,
    country: str = "norway",
    days: int = 1825,
    min_score: float = 0.01,
    max_volatility: float = 0.06,
    data_source: str = "auto",
) -> dict:
    data_source = data_source.strip().lower()
    raw_df = get_stock_data(symbol, country=country, days=days, source=data_source)
    df = add_technical_indicators(raw_df)
    metrics = compute_stock_metrics(df)
    scorecard = build_scorecard(metrics, min_score=min_score, max_volatility=max_volatility)
    technical = compute_technical_overview(df)
    fundamentals = get_stock_fundamentals(symbol, country=country, source=data_source)

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
        "name": name,
        "country": country,
        "exchange": exchange,
        "data_source": data_source,
        "data": df,
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
) -> list[dict]:
    results: list[dict] = []
    for symbol in symbols:
        try:
            result = analyze_stock(
                symbol,
                country=country,
                days=days,
                min_score=min_score,
                max_volatility=max_volatility,
                data_source=data_source,
            )
            results.append(result)
        except Exception as exc:
            results.append({"symbol": symbol, "error": str(exc)})
    return results
