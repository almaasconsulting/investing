from __future__ import annotations

from itertools import combinations
from typing import Iterable

import pandas as pd

from investing.db.store import query_stock_histories


def build_close_price_matrix(
    symbols: Iterable[str],
    country_by_symbol: dict[str, str],
    days: int,
) -> tuple[pd.DataFrame, list[dict]]:
    """Build a close-price matrix exclusively from persisted PostgreSQL data."""
    requested = list(dict.fromkeys(str(symbol).strip() for symbol in symbols))
    stocks = [
        (symbol, country_by_symbol.get(symbol, "norway"))
        for symbol in requested
        if symbol
    ]
    history = query_stock_histories(stocks, days=days)
    if history.empty:
        errors = [
            {
                "symbol": symbol,
                "country": country,
                "error": "No stored price history in the selected date range.",
            }
            for symbol, country in stocks
        ]
        return pd.DataFrame(), errors

    history = history.copy()
    history["date"] = pd.to_datetime(history["date"], errors="coerce")
    history["close"] = pd.to_numeric(history["close"], errors="coerce")
    history = history.dropna(subset=["date", "symbol", "close"])
    matrix = (
        history.pivot_table(
            index="date",
            columns="symbol",
            values="close",
            aggfunc="last",
        )
        .sort_index()
        .dropna(axis=1, how="all")
    )
    matrix.columns.name = None

    available = {str(symbol).lower() for symbol in matrix.columns}
    errors = [
        {
            "symbol": symbol,
            "country": country,
            "error": "No stored price history in the selected date range.",
        }
        for symbol, country in stocks
        if symbol.lower() not in available
    ]
    return matrix, errors


def compute_return_correlation(price_matrix: pd.DataFrame) -> pd.DataFrame:
    if price_matrix.empty:
        return pd.DataFrame()
    returns = price_matrix.pct_change().dropna(how="all")
    return returns.corr()


def cluster_by_correlation(correlation: pd.DataFrame, min_correlation: float = 0.65) -> pd.DataFrame:
    if correlation.empty:
        return pd.DataFrame(columns=["cluster", "symbol", "members", "average_correlation"])

    unassigned = set(correlation.columns)
    clusters: list[dict] = []
    cluster_id = 1

    while unassigned:
        seed = sorted(unassigned)[0]
        related = {
            symbol
            for symbol in unassigned
            if symbol == seed or correlation.loc[seed, symbol] >= min_correlation
        }
        for symbol in related:
            unassigned.remove(symbol)

        members = sorted(related)
        if len(members) > 1:
            values = [
                float(correlation.loc[left, right])
                for left, right in combinations(members, 2)
                if pd.notna(correlation.loc[left, right])
            ]
            average = sum(values) / len(values) if values else 1.0
        else:
            average = 1.0

        for symbol in members:
            clusters.append(
                {
                    "cluster": cluster_id,
                    "symbol": symbol,
                    "members": ", ".join(members),
                    "average_correlation": average,
                }
            )
        cluster_id += 1

    return pd.DataFrame(clusters)


def correlation_pairs(correlation: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for left, right in combinations(correlation.columns, 2):
        value = correlation.loc[left, right]
        if pd.notna(value):
            rows.append(
                {
                    "symbol_a": left,
                    "symbol_b": right,
                    "correlation": float(value),
                    "distance": float(1 - value),
                }
            )
    if not rows:
        return pd.DataFrame(columns=["symbol_a", "symbol_b", "correlation", "distance"])
    return pd.DataFrame(rows).sort_values("correlation", ascending=False)
