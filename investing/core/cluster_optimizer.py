from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from investing.core.clustering import (
    agglomerative_cluster_solutions,
    build_stock_similarity,
)


DEFAULT_FUNDAMENTAL_WEIGHTS = (0.0, 0.15, 0.30, 0.45)
DEFAULT_PERFORMANCE_WEIGHTS = (0.10, 0.25, 0.40)
DEFAULT_LINKAGES = ("average", "complete")


def _labels_from_clusters(clusters: pd.DataFrame) -> dict[str, int]:
    return {
        str(row.symbol): int(row.cluster)
        for row in clusters.itertuples(index=False)
    }


def silhouette_score(
    similarity: pd.DataFrame,
    labels: dict[str, int],
) -> float:
    """Calculate a mean silhouette score directly from a similarity matrix."""
    symbols = [
        symbol
        for symbol in similarity.columns
        if symbol in labels
    ]
    if len(symbols) < 3 or len(set(labels[symbol] for symbol in symbols)) < 2:
        return np.nan

    distance = 1.0 - similarity.reindex(
        index=symbols,
        columns=symbols,
    ).clip(lower=-1.0, upper=1.0).to_numpy(dtype=float)
    label_values = np.asarray([labels[symbol] for symbol in symbols])
    unique_labels = np.unique(label_values)
    scores: list[float] = []
    for position, own_label in enumerate(label_values):
        own_mask = label_values == own_label
        own_mask[position] = False
        if not own_mask.any():
            scores.append(0.0)
            continue

        within = distance[position, own_mask]
        within = within[np.isfinite(within)]
        if not within.size:
            continue
        other_averages = []
        for other_label in unique_labels:
            if other_label == own_label:
                continue
            values = distance[position, label_values == other_label]
            values = values[np.isfinite(values)]
            if values.size:
                other_averages.append(float(values.mean()))
        if not other_averages:
            continue

        a = float(within.mean())
        b = min(other_averages)
        denominator = max(a, b)
        scores.append((b - a) / denominator if denominator > 0 else 0.0)
    return float(np.mean(scores)) if scores else np.nan


def _cluster_penalties(clusters: pd.DataFrame) -> tuple[float, float]:
    sizes = clusters.groupby("cluster")["symbol"].count()
    if sizes.empty:
        return 1.0, 1.0
    singleton_fraction = float(sizes.eq(1).sum() / len(sizes))
    largest_cluster_fraction = float(sizes.max() / sizes.sum())
    imbalance = max(0.0, largest_cluster_fraction - 0.50)
    return singleton_fraction, imbalance


def _candidate_cluster_counts(stock_count: int) -> list[int]:
    if stock_count < 3:
        return []
    lower = 2 if stock_count < 8 else 4
    upper = min(16, max(lower, stock_count // 2), stock_count - 1)
    return list(range(lower, upper + 1))


def _blend_components(
    components: dict[str, pd.DataFrame],
    fundamental_weight: float,
    performance_weight: float,
) -> pd.DataFrame:
    returns_frame = components["return_correlation"]
    symbols = list(returns_frame.columns)
    performance_frame = components["performance_similarity"].reindex(
        index=symbols,
        columns=symbols,
    )
    fundamentals_frame = components["fundamental_similarity"].reindex(
        index=symbols,
        columns=symbols,
    )
    returns = returns_frame.to_numpy(dtype=float)
    performance = performance_frame.to_numpy(dtype=float)
    fundamentals = fundamentals_frame.to_numpy(dtype=float)
    market = np.where(
        np.isfinite(returns) & np.isfinite(performance),
        (1.0 - performance_weight) * returns
        + performance_weight * performance,
        np.where(np.isfinite(returns), returns, performance),
    )
    combined = np.where(
        np.isfinite(market) & np.isfinite(fundamentals),
        (1.0 - fundamental_weight) * market
        + fundamental_weight * fundamentals,
        np.where(np.isfinite(market), market, fundamentals),
    )
    np.fill_diagonal(combined, 1.0)
    return pd.DataFrame(combined, index=symbols, columns=symbols)


def optimize_stock_clusters(
    price_matrix: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    fundamental_weights: Iterable[float] = DEFAULT_FUNDAMENTAL_WEIGHTS,
    performance_weights: Iterable[float] = DEFAULT_PERFORMANCE_WEIGHTS,
    linkages: Iterable[str] = DEFAULT_LINKAGES,
    validation_fraction: float = 0.30,
) -> dict:
    """Tune clustering parameters on stored history with chronological validation."""
    clean_prices = price_matrix.sort_index().dropna(axis=1, thresh=3)
    if clean_prices.shape[1] < 3:
        raise ValueError("At least three stocks with stored prices are required.")
    if len(clean_prices) < 45:
        raise ValueError(
            "At least 45 stored trading dates are required for train/validation tuning."
        )
    if not 0.15 <= validation_fraction <= 0.45:
        raise ValueError("validation_fraction must be between 0.15 and 0.45")

    split_at = int(round(len(clean_prices) * (1.0 - validation_fraction)))
    split_at = min(max(split_at, 30), len(clean_prices) - 15)
    train_prices = clean_prices.iloc[:split_at]
    validation_prices = clean_prices.iloc[split_at:]
    cluster_counts = _candidate_cluster_counts(clean_prices.shape[1])
    trials: list[dict] = []
    train_components = build_stock_similarity(
        train_prices,
        metadata,
        fundamental_weight=0.0,
        performance_weight=0.0,
    )
    validation_components = build_stock_similarity(
        validation_prices,
        metadata,
        fundamental_weight=0.0,
        performance_weight=0.0,
    )
    full_components = build_stock_similarity(
        clean_prices,
        metadata,
        fundamental_weight=0.0,
        performance_weight=0.0,
    )

    for fundamental_weight in fundamental_weights:
        for performance_weight in performance_weights:
            train_similarity = _blend_components(
                train_components,
                float(fundamental_weight),
                float(performance_weight),
            )
            validation_similarity = _blend_components(
                validation_components,
                float(fundamental_weight),
                float(performance_weight),
            )
            full_similarity = _blend_components(
                full_components,
                float(fundamental_weight),
                float(performance_weight),
            )
            for linkage in linkages:
                solutions = agglomerative_cluster_solutions(
                    train_similarity,
                    cluster_counts,
                    linkage=str(linkage),
                )
                full_solutions = agglomerative_cluster_solutions(
                    full_similarity,
                    cluster_counts,
                    linkage=str(linkage),
                )
                for cluster_count, clusters in solutions.items():
                    labels = _labels_from_clusters(clusters)
                    full_clusters = full_solutions[cluster_count]
                    train_score = silhouette_score(train_similarity, labels)
                    validation_score = silhouette_score(
                        validation_similarity,
                        labels,
                    )
                    full_labels = _labels_from_clusters(full_clusters)
                    full_score = silhouette_score(full_similarity, full_labels)
                    singleton_fraction, imbalance = _cluster_penalties(
                        full_clusters
                    )
                    largest_cluster_fraction = float(
                        full_clusters.groupby("cluster")["symbol"].count().max()
                        / len(full_clusters)
                    )
                    portfolio_usable = (
                        singleton_fraction == 0.0
                        and largest_cluster_fraction <= 0.60
                    )
                    valid_train = (
                        0.0 if not np.isfinite(train_score) else train_score
                    )
                    valid_validation = (
                        0.0
                        if not np.isfinite(validation_score)
                        else validation_score
                    )
                    objective = (
                        0.40 * valid_train
                        + 0.60 * valid_validation
                        - 0.10 * singleton_fraction
                        - 0.05 * imbalance
                    )
                    trials.append(
                        {
                            "linkage": str(linkage),
                            "cluster_count": int(cluster_count),
                            "fundamental_weight": float(fundamental_weight),
                            "performance_weight": float(performance_weight),
                            "co_movement_weight": float(
                                (1.0 - fundamental_weight)
                                * (1.0 - performance_weight)
                            ),
                            "realized_performance_weight": float(
                                (1.0 - fundamental_weight)
                                * performance_weight
                            ),
                            "train_silhouette": float(train_score),
                            "validation_silhouette": float(validation_score),
                            "full_silhouette": float(full_score),
                            "singleton_fraction": singleton_fraction,
                            "largest_cluster_fraction": largest_cluster_fraction,
                            "portfolio_usable": portfolio_usable,
                            "objective": float(objective),
                        }
                    )

    trials_frame = pd.DataFrame(trials).sort_values(
        [
            "portfolio_usable",
            "objective",
            "validation_silhouette",
            "train_silhouette",
            "cluster_count",
        ],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)
    if trials_frame.empty:
        raise ValueError("No valid clustering parameter combinations were found.")

    best = trials_frame.iloc[0].to_dict()
    best["cluster_count"] = int(best["cluster_count"])
    full_components = build_stock_similarity(
        clean_prices,
        metadata,
        fundamental_weight=float(best["fundamental_weight"]),
        performance_weight=float(best["performance_weight"]),
    )
    best_clusters = agglomerative_cluster_solutions(
        full_components["similarity"],
        [int(best["cluster_count"])],
        linkage=str(best["linkage"]),
    )[int(best["cluster_count"])]
    return {
        "best": best,
        "trials": trials_frame,
        "clusters": best_clusters,
        "components": full_components,
        "train_dates": len(train_prices),
        "validation_dates": len(validation_prices),
        "split_date": validation_prices.index.min(),
    }
