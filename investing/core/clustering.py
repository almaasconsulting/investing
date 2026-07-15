from __future__ import annotations

from itertools import combinations
from typing import Iterable

import pandas as pd

from investing.data_fetch.investing_com import get_stock_data


def build_close_price_matrix(
    symbols: Iterable[str],
    country_by_symbol: dict[str, str],
    days: int,
    data_source: str = "yahoo",
) -> tuple[pd.DataFrame, list[dict]]:
    prices: dict[str, pd.Series] = {}
    errors: list[dict] = []

    for symbol in symbols:
        country = country_by_symbol.get(symbol, "norway")
        try:
            df = get_stock_data(symbol, country=country, days=days, source=data_source)
            series = df.sort_values("date").set_index("date")["close"].rename(symbol)
            prices[symbol] = series
        except Exception as exc:
            errors.append({"symbol": symbol, "country": country, "error": str(exc)})

    if not prices:
        return pd.DataFrame(), errors

    matrix = pd.concat(prices.values(), axis=1).sort_index()
    return matrix.dropna(axis=1, how="all"), errors


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
