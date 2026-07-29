from __future__ import annotations

import heapq
from itertools import combinations
from typing import Iterable

import numpy as np
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
    returns = price_matrix.pct_change(fill_method=None).dropna(how="all")
    return returns.corr()


def _rank_feature_similarity(
    features: pd.DataFrame,
    symbols: Iterable[str],
) -> pd.DataFrame:
    """Convert numeric feature proximity into a 0..1 pairwise similarity."""
    ordered_symbols = list(dict.fromkeys(str(symbol) for symbol in symbols))
    if not ordered_symbols:
        return pd.DataFrame()
    prepared = features.reindex(ordered_symbols).apply(
        pd.to_numeric,
        errors="coerce",
    )
    ranked = prepared.rank(pct=True, method="average")
    result = pd.DataFrame(
        np.nan,
        index=ordered_symbols,
        columns=ordered_symbols,
        dtype=float,
    )
    for index, left in enumerate(ordered_symbols):
        result.loc[left, left] = 1.0
        for right in ordered_symbols[index + 1:]:
            common = ranked.loc[[left, right]].dropna(axis=1)
            if common.empty:
                continue
            distance = float(
                (common.loc[left] - common.loc[right]).abs().mean()
            )
            similarity = float(np.clip(1.0 - distance, 0.0, 1.0))
            result.loc[left, right] = similarity
            result.loc[right, left] = similarity
    return result


def compute_performance_similarity(price_matrix: pd.DataFrame) -> pd.DataFrame:
    """Compare total return, risk, drawdown, and positive-day frequency."""
    if price_matrix.empty:
        return pd.DataFrame()
    returns = price_matrix.pct_change(fill_method=None)
    total_return = price_matrix.apply(
        lambda series: (
            series.dropna().iloc[-1] / series.dropna().iloc[0] - 1.0
            if len(series.dropna()) >= 2 and series.dropna().iloc[0] != 0
            else np.nan
        )
    )
    volatility = returns.std(skipna=True) * np.sqrt(252.0)
    downside_volatility = returns.where(returns < 0).std(skipna=True) * np.sqrt(252.0)
    drawdown = (price_matrix / price_matrix.cummax() - 1.0).min().abs()
    positive_day_share = (returns > 0).sum() / returns.notna().sum().replace(0, np.nan)
    features = pd.DataFrame(
        {
            "total_return": total_return,
            "volatility": volatility,
            "downside_volatility": downside_volatility,
            "max_drawdown": drawdown,
            "positive_day_share": positive_day_share,
        }
    )
    return _rank_feature_similarity(features, price_matrix.columns)


def compute_fundamental_similarity(
    metadata: pd.DataFrame,
    symbols: Iterable[str],
) -> pd.DataFrame:
    """Compare a compact set of essential persisted fundamental factors."""
    ordered_symbols = list(dict.fromkeys(str(symbol) for symbol in symbols))
    factor_columns = [
        "market_cap",
        "pe_ratio",
        "price_to_book",
        "return_on_equity",
        "profit_margins",
        "revenue_growth",
        "earnings_growth",
        "debt_to_equity",
        "current_ratio",
        "dividend_yield",
        "dividend_payer",
    ]
    if metadata.empty or "symbol" not in metadata.columns:
        return pd.DataFrame(
            np.nan,
            index=ordered_symbols,
            columns=ordered_symbols,
        )
    available = [
        column for column in factor_columns if column in metadata.columns
    ]
    features = (
        metadata.drop_duplicates("symbol")
        .set_index("symbol")
        .reindex(ordered_symbols)[available]
    )
    return _rank_feature_similarity(features, ordered_symbols)


def build_stock_similarity(
    price_matrix: pd.DataFrame,
    metadata: pd.DataFrame,
    fundamental_weight: float = 0.25,
) -> dict[str, pd.DataFrame]:
    """Blend co-movement, realized performance, and fundamental similarity."""
    if not 0.0 <= fundamental_weight <= 1.0:
        raise ValueError("fundamental_weight must be between 0 and 1")
    return_correlation = compute_return_correlation(price_matrix)
    if return_correlation.empty:
        return {
            "similarity": pd.DataFrame(),
            "return_correlation": pd.DataFrame(),
            "performance_similarity": pd.DataFrame(),
            "fundamental_similarity": pd.DataFrame(),
        }

    symbols = list(return_correlation.columns)
    performance_similarity = compute_performance_similarity(price_matrix).reindex(
        index=symbols,
        columns=symbols,
    )
    fundamental_similarity = compute_fundamental_similarity(
        metadata,
        symbols,
    ).reindex(index=symbols, columns=symbols)

    returns = return_correlation.to_numpy(dtype=float)
    performance = performance_similarity.to_numpy(dtype=float)
    fundamentals = fundamental_similarity.to_numpy(dtype=float)
    market_similarity = np.where(
        np.isfinite(returns) & np.isfinite(performance),
        0.80 * returns + 0.20 * performance,
        np.where(np.isfinite(returns), returns, performance),
    )
    combined = np.where(
        np.isfinite(market_similarity) & np.isfinite(fundamentals),
        (1.0 - fundamental_weight) * market_similarity
        + fundamental_weight * fundamentals,
        np.where(np.isfinite(market_similarity), market_similarity, fundamentals),
    )
    np.fill_diagonal(combined, 1.0)
    similarity = pd.DataFrame(combined, index=symbols, columns=symbols)
    return {
        "similarity": similarity,
        "return_correlation": return_correlation,
        "performance_similarity": performance_similarity,
        "fundamental_similarity": fundamental_similarity,
    }


def _consolidate_cluster_members(
    correlation: pd.DataFrame,
    groups: dict[int, list[str]],
    max_clusters: int,
) -> dict[int, list[str]]:
    """Merge the most similar groups until the requested cap is reached."""
    if len(groups) <= max_clusters:
        return groups

    symbols = list(correlation.columns)
    position_by_symbol = {
        symbol: position for position, symbol in enumerate(symbols)
    }
    correlation_values = correlation.reindex(
        index=symbols,
        columns=symbols,
    ).to_numpy(dtype=float)
    positions_by_group = {
        group_id: np.asarray(
            [position_by_symbol[symbol] for symbol in members],
            dtype=int,
        )
        for group_id, members in groups.items()
    }
    pair_stats: dict[tuple[int, int], tuple[float, int]] = {}
    similarity_heap: list[tuple[float, int, int]] = []
    for left_id, right_id in combinations(sorted(groups), 2):
        values = correlation_values[
            np.ix_(positions_by_group[left_id], positions_by_group[right_id])
        ]
        finite = values[np.isfinite(values)]
        stats = (
            float(finite.sum()) if finite.size else 0.0,
            int(finite.size),
        )
        pair_stats[(left_id, right_id)] = stats
        if stats[1]:
            heapq.heappush(
                similarity_heap,
                (-(stats[0] / stats[1]), left_id, right_id),
            )

    while len(groups) > max_clusters:
        best_pair = None
        while similarity_heap:
            negative_similarity, left_id, right_id = heapq.heappop(
                similarity_heap
            )
            pair = (left_id, right_id)
            current = pair_stats.get(pair)
            if (
                left_id in groups
                and right_id in groups
                and current is not None
                and current[1]
                and np.isclose(-negative_similarity, current[0] / current[1])
            ):
                best_pair = pair
                break

        if best_pair is None:
            ordered = sorted(groups, key=lambda group_id: (len(groups[group_id]), group_id))
            best_pair = tuple(sorted(ordered[:2]))

        left_id, right_id = best_pair
        other_ids = [
            group_id for group_id in groups if group_id not in {left_id, right_id}
        ]
        merged_stats = {}
        for other_id in other_ids:
            left_key = tuple(sorted((left_id, other_id)))
            right_key = tuple(sorted((right_id, other_id)))
            left_total, left_count = pair_stats.get(left_key, (0.0, 0))
            right_total, right_count = pair_stats.get(right_key, (0.0, 0))
            merged_stats[tuple(sorted((left_id, other_id)))] = (
                left_total + right_total,
                left_count + right_count,
            )

        pair_stats = {
            pair: stats
            for pair, stats in pair_stats.items()
            if left_id not in pair and right_id not in pair
        }
        pair_stats.update(merged_stats)
        for pair, (total, count) in merged_stats.items():
            if count:
                heapq.heappush(
                    similarity_heap,
                    (-(total / count), pair[0], pair[1]),
                )
        groups[left_id] = sorted(groups[left_id] + groups[right_id])
        del groups[right_id]

    return groups


def cluster_by_correlation(
    correlation: pd.DataFrame,
    min_correlation: float = 0.65,
    max_clusters: int | None = 12,
) -> pd.DataFrame:
    if correlation.empty:
        return pd.DataFrame(columns=["cluster", "symbol", "members", "average_correlation"])
    if max_clusters is not None and max_clusters < 1:
        raise ValueError("max_clusters must be at least 1")

    ordered_symbols = sorted(correlation.columns)
    correlation_values = correlation.reindex(
        index=ordered_symbols,
        columns=ordered_symbols,
    ).to_numpy(dtype=float)
    unassigned = set(range(len(ordered_symbols)))
    member_groups: dict[int, list[str]] = {}
    cluster_id = 1

    while unassigned:
        seed = min(unassigned)
        related = {
            position
            for position in unassigned
            if position == seed
            or correlation_values[seed, position] >= min_correlation
        }
        unassigned.difference_update(related)

        member_groups[cluster_id] = [
            ordered_symbols[position] for position in sorted(related)
        ]
        cluster_id += 1

    if max_clusters is not None:
        member_groups = _consolidate_cluster_members(
            correlation,
            member_groups,
            max_clusters=max_clusters,
        )

    clusters: list[dict] = []
    for output_cluster_id, source_cluster_id in enumerate(sorted(member_groups), start=1):
        members = member_groups[source_cluster_id]
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
                    "cluster": output_cluster_id,
                    "symbol": symbol,
                    "members": ", ".join(members),
                    "average_correlation": average,
                }
            )

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


def cluster_distance_matrix(
    correlation: pd.DataFrame,
    clusters: pd.DataFrame,
) -> pd.DataFrame:
    """Average pairwise similarity distance between every cluster."""
    if correlation.empty or clusters.empty:
        return pd.DataFrame()

    members_by_cluster = {
        cluster_id: group["symbol"].astype(str).tolist()
        for cluster_id, group in clusters.groupby("cluster", sort=True)
    }
    cluster_ids = list(members_by_cluster)
    distances = pd.DataFrame(
        np.nan,
        index=cluster_ids,
        columns=cluster_ids,
        dtype=float,
    )
    for cluster_id in cluster_ids:
        distances.loc[cluster_id, cluster_id] = 0.0

    for left_id, right_id in combinations(cluster_ids, 2):
        left = members_by_cluster[left_id]
        right = members_by_cluster[right_id]
        values = correlation.reindex(index=left, columns=right).to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size:
            distance = float(np.clip(1.0 - finite.mean(), 0.0, 2.0))
            distances.loc[left_id, right_id] = distance
            distances.loc[right_id, left_id] = distance
    return distances


def cluster_network_layout(
    distances: pd.DataFrame,
    dimensions: int = 2,
) -> pd.DataFrame:
    """Project cluster distances into two or three dimensions with classical MDS."""
    if dimensions not in {2, 3}:
        raise ValueError("dimensions must be 2 or 3")
    if distances.empty:
        return pd.DataFrame(columns=["cluster", "x", "y", "z"])

    cluster_ids = list(distances.index)
    count = len(cluster_ids)
    if count == 1:
        return pd.DataFrame(
            [{"cluster": cluster_ids[0], "x": 0.0, "y": 0.0, "z": 0.0}]
        )

    values = distances.to_numpy(dtype=float)
    finite_off_diagonal = values[
        np.isfinite(values) & ~np.eye(count, dtype=bool)
    ]
    fallback = float(np.median(finite_off_diagonal)) if finite_off_diagonal.size else 1.0
    values = np.where(np.isfinite(values), values, fallback)
    values = (values + values.T) / 2.0
    np.fill_diagonal(values, 0.0)

    centering = np.eye(count) - np.ones((count, count)) / count
    gram = -0.5 * centering @ (values ** 2) @ centering
    eigenvalues, eigenvectors = np.linalg.eigh(gram)
    order = np.argsort(eigenvalues)[::-1]
    positive = [
        index for index in order if eigenvalues[index] > 1e-12
    ][:dimensions]
    coordinates = np.zeros((count, 3), dtype=float)
    for axis, index in enumerate(positive):
        coordinates[:, axis] = eigenvectors[:, index] * np.sqrt(eigenvalues[index])

    return pd.DataFrame(
        {
            "cluster": cluster_ids,
            "x": coordinates[:, 0],
            "y": coordinates[:, 1],
            "z": coordinates[:, 2],
        }
    )


def nearest_cluster_edges(
    distances: pd.DataFrame,
    links_per_cluster: int = 1,
) -> pd.DataFrame:
    """Return a readable subset of closest inter-cluster connections."""
    columns = ["cluster_a", "cluster_b", "distance", "correlation"]
    if distances.empty or len(distances) < 2:
        return pd.DataFrame(columns=columns)

    links_per_cluster = max(1, int(links_per_cluster))
    selected: set[tuple[object, object]] = set()
    order = {cluster_id: index for index, cluster_id in enumerate(distances.index)}
    for cluster_id in distances.index:
        candidates = distances.loc[cluster_id].drop(index=cluster_id).dropna()
        for other_id in candidates.nsmallest(links_per_cluster).index:
            pair = tuple(
                sorted((cluster_id, other_id), key=lambda value: order[value])
            )
            selected.add(pair)

    rows = [
        {
            "cluster_a": left,
            "cluster_b": right,
            "distance": float(distances.loc[left, right]),
            "correlation": float(1.0 - distances.loc[left, right]),
        }
        for left, right in selected
    ]
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["distance", "cluster_a", "cluster_b"]
    )


def _average_within_cluster(
    correlation: pd.DataFrame,
    members: list[str],
) -> float:
    values = [
        float(correlation.loc[left, right])
        for left, right in combinations(members, 2)
        if left in correlation.index
        and right in correlation.columns
        and pd.notna(correlation.loc[left, right])
    ]
    return float(np.mean(values)) if values else 1.0


def _dominant_profile(
    metadata: pd.DataFrame,
    members: list[str],
    column: str,
) -> str:
    if metadata.empty or column not in metadata.columns:
        return "Unknown"
    values = metadata[
        metadata["symbol"].astype(str).isin(members)
    ][column].dropna().astype(str)
    values = values[~values.str.lower().isin({"", "none", "unknown"})]
    if values.empty:
        return "Unknown"
    counts = values.value_counts()
    share = 100.0 * counts.iloc[0] / counts.sum()
    return f"{counts.index[0]} ({share:.0f}%)"


def _distance_meaning(distance: float) -> str:
    if distance <= 0.35:
        return "very close; the blended stock profiles are similar"
    if distance <= 0.70:
        return "moderately close; the profiles share several characteristics"
    if distance <= 1.00:
        return "far apart; the profiles have limited similarity"
    return "very far apart; return movement is often opposing or profiles differ strongly"


def _average_between_clusters(
    matrix: pd.DataFrame,
    left_members: list[str],
    right_members: list[str],
) -> float:
    if matrix.empty:
        return np.nan
    values = matrix.reindex(
        index=left_members,
        columns=right_members,
    ).to_numpy(dtype=float)
    finite = values[np.isfinite(values)]
    return float(finite.mean()) if finite.size else np.nan


def cluster_relationship_summary(
    correlation: pd.DataFrame,
    clusters: pd.DataFrame,
    metadata: pd.DataFrame | None = None,
    return_correlation: pd.DataFrame | None = None,
    fundamental_similarity: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Describe cluster composition and exact nearest/farthest relationships."""
    columns = [
        "cluster",
        "stock_count",
        "members",
        "dominant_sector",
        "dominant_country",
        "within_similarity",
        "nearest_cluster",
        "nearest_similarity",
        "nearest_distance",
        "nearest_return_correlation",
        "nearest_fundamental_similarity",
        "farthest_cluster",
        "farthest_similarity",
        "farthest_distance",
        "farthest_return_correlation",
        "farthest_fundamental_similarity",
        "interpretation",
    ]
    if correlation.empty or clusters.empty:
        return pd.DataFrame(columns=columns)

    metadata = metadata.copy() if metadata is not None else pd.DataFrame()
    return_correlation = (
        return_correlation if return_correlation is not None else correlation
    )
    fundamental_similarity = (
        fundamental_similarity
        if fundamental_similarity is not None
        else pd.DataFrame()
    )
    distances = cluster_distance_matrix(correlation, clusters)
    members_by_cluster = {
        cluster_id: group["symbol"].astype(str).tolist()
        for cluster_id, group in clusters.groupby("cluster", sort=True)
    }
    rows = []
    for cluster_id, group in clusters.groupby("cluster", sort=True):
        members = sorted(group["symbol"].astype(str).tolist())
        other_distances = distances.loc[cluster_id].drop(index=cluster_id).dropna()
        nearest_id = other_distances.idxmin() if not other_distances.empty else None
        farthest_id = other_distances.idxmax() if not other_distances.empty else None
        nearest_distance = (
            float(other_distances.loc[nearest_id]) if nearest_id is not None else np.nan
        )
        farthest_distance = (
            float(other_distances.loc[farthest_id]) if farthest_id is not None else np.nan
        )
        within = _average_within_cluster(correlation, members)
        nearest_members = members_by_cluster.get(nearest_id, [])
        farthest_members = members_by_cluster.get(farthest_id, [])
        nearest_return = _average_between_clusters(
            return_correlation,
            members,
            nearest_members,
        )
        nearest_fundamental = _average_between_clusters(
            fundamental_similarity,
            members,
            nearest_members,
        )
        farthest_return = _average_between_clusters(
            return_correlation,
            members,
            farthest_members,
        )
        farthest_fundamental = _average_between_clusters(
            fundamental_similarity,
            members,
            farthest_members,
        )
        sector = _dominant_profile(metadata, members, "sector")
        country = _dominant_profile(metadata, members, "country")

        interpretation_parts = [
            f"Internal blended similarity is {within:.2f}."
        ]
        if nearest_id is not None:
            interpretation_parts.append(
                f"Cluster {nearest_id} is nearest ({_distance_meaning(nearest_distance)})."
            )
            if np.isfinite(nearest_return):
                interpretation_parts.append(
                    f"Its average return correlation is {nearest_return:.2f}"
                    + (
                        f" and fundamental similarity is {nearest_fundamental:.2f}."
                        if np.isfinite(nearest_fundamental)
                        else "."
                    )
                )
        if farthest_id is not None:
            interpretation_parts.append(
                f"Cluster {farthest_id} is farthest ({_distance_meaning(farthest_distance)})."
            )
            if np.isfinite(farthest_return):
                interpretation_parts.append(
                    f"Its average return correlation is {farthest_return:.2f}"
                    + (
                        f" and fundamental similarity is {farthest_fundamental:.2f}."
                        if np.isfinite(farthest_fundamental)
                        else "."
                    )
                )
        profile_parts = []
        if sector != "Unknown":
            profile_parts.append(f"sector: {sector}")
        if country != "Unknown":
            profile_parts.append(f"country: {country}")
        if profile_parts:
            interpretation_parts.append(
                "Shared exposure may partly explain the pattern ("
                + "; ".join(profile_parts)
                + "), but correlation alone does not establish the cause."
            )
        else:
            interpretation_parts.append(
                "The pattern describes realized return movement; correlation alone "
                "does not establish its economic cause."
            )

        rows.append(
            {
                "cluster": f"Cluster {cluster_id}",
                "stock_count": len(members),
                "members": ", ".join(members),
                "dominant_sector": sector,
                "dominant_country": country,
                "within_similarity": within,
                "nearest_cluster": (
                    f"Cluster {nearest_id}" if nearest_id is not None else "None"
                ),
                "nearest_similarity": (
                    1.0 - nearest_distance if nearest_id is not None else np.nan
                ),
                "nearest_distance": nearest_distance,
                "nearest_return_correlation": nearest_return,
                "nearest_fundamental_similarity": nearest_fundamental,
                "farthest_cluster": (
                    f"Cluster {farthest_id}" if farthest_id is not None else "None"
                ),
                "farthest_similarity": (
                    1.0 - farthest_distance if farthest_id is not None else np.nan
                ),
                "farthest_distance": farthest_distance,
                "farthest_return_correlation": farthest_return,
                "farthest_fundamental_similarity": farthest_fundamental,
                "interpretation": " ".join(interpretation_parts),
            }
        )
    return pd.DataFrame(rows, columns=columns)
