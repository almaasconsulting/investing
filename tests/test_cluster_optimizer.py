from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from investing.core.cluster_optimizer import (
    optimize_stock_clusters,
    silhouette_score,
)


class ClusterOptimizerTests(unittest.TestCase):
    def test_silhouette_rewards_compact_separated_groups(self) -> None:
        similarity = pd.DataFrame(
            [
                [1.0, 0.9, 0.1, 0.0],
                [0.9, 1.0, 0.0, 0.1],
                [0.1, 0.0, 1.0, 0.8],
                [0.0, 0.1, 0.8, 1.0],
            ],
            index=["A", "B", "C", "D"],
            columns=["A", "B", "C", "D"],
        )

        score = silhouette_score(
            similarity,
            {"A": 1, "B": 1, "C": 2, "D": 2},
        )

        self.assertGreater(score, 0.75)

    def test_optimizer_returns_validated_database_price_solution(self) -> None:
        random = np.random.default_rng(7)
        dates = pd.date_range("2025-01-01", periods=100)
        factor_one = random.normal(0.001, 0.01, len(dates) - 1)
        factor_two = random.normal(-0.0005, 0.012, len(dates) - 1)
        prices = {}
        for index, symbol in enumerate(["A", "B", "C"]):
            noise = random.normal(0, 0.001, len(factor_one))
            prices[symbol] = np.r_[100, 100 * (1 + factor_one + noise).cumprod()]
        for index, symbol in enumerate(["D", "E", "F"]):
            noise = random.normal(0, 0.001, len(factor_two))
            prices[symbol] = np.r_[100, 100 * (1 + factor_two + noise).cumprod()]
        price_matrix = pd.DataFrame(prices, index=dates)
        metadata = pd.DataFrame(
            [{"symbol": symbol, "pe_ratio": 10 + index}
             for index, symbol in enumerate(prices)]
        )

        result = optimize_stock_clusters(
            price_matrix,
            metadata,
            fundamental_weights=[0.0],
            performance_weights=[0.1],
        )

        self.assertFalse(result["trials"].empty)
        self.assertEqual(set(result["clusters"]["symbol"]), set(prices))
        self.assertGreater(result["validation_dates"], 0)
        self.assertIn(int(result["best"]["cluster_count"]), range(2, 4))
        self.assertIn("portfolio_usable", result["trials"].columns)

    def test_optimizer_rejects_too_little_history(self) -> None:
        with self.assertRaisesRegex(ValueError, "45 stored trading dates"):
            optimize_stock_clusters(
                pd.DataFrame(
                    np.ones((30, 3)),
                    columns=["A", "B", "C"],
                ),
                pd.DataFrame({"symbol": ["A", "B", "C"]}),
            )


if __name__ == "__main__":
    unittest.main()
