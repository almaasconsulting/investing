from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from investing.core.clustering import build_close_price_matrix
from investing.core.clustering import (
    agglomerative_cluster_solutions,
    build_stock_similarity,
    cluster_by_correlation,
    cluster_distance_matrix,
    cluster_network_layout,
    cluster_relationship_summary,
    nearest_cluster_edges,
)


class DatabaseClusteringTests(unittest.TestCase):
    def test_complete_linkage_builds_requested_partition(self) -> None:
        symbols = ["AAA", "AAB", "BBB", "BBC"]
        similarity = pd.DataFrame(
            [
                [1.0, 0.9, 0.2, 0.1],
                [0.9, 1.0, 0.1, 0.2],
                [0.2, 0.1, 1.0, 0.8],
                [0.1, 0.2, 0.8, 1.0],
            ],
            index=symbols,
            columns=symbols,
        )

        clusters = agglomerative_cluster_solutions(
            similarity,
            [2],
            linkage="complete",
        )[2]
        labels = clusters.set_index("symbol")["cluster"].to_dict()

        self.assertEqual(labels["AAA"], labels["AAB"])
        self.assertEqual(labels["BBB"], labels["BBC"])
        self.assertNotEqual(labels["AAA"], labels["BBB"])

    @patch("investing.core.clustering.query_stock_histories")
    def test_price_matrix_uses_bulk_stored_history(self, query_histories) -> None:
        query_histories.return_value = pd.DataFrame(
            [
                {"date": "2026-01-02", "symbol": "AAA", "country": "norway", "close": 10.0},
                {"date": "2026-01-03", "symbol": "AAA", "country": "norway", "close": 11.0},
                {"date": "2026-01-02", "symbol": "BBB", "country": "sweden", "close": 20.0},
            ]
        )

        matrix, errors = build_close_price_matrix(
            ["AAA", "BBB"],
            {"AAA": "norway", "BBB": "sweden"},
            days=90,
        )

        query_histories.assert_called_once_with(
            [("AAA", "norway"), ("BBB", "sweden")],
            days=90,
        )
        self.assertEqual(list(matrix.columns), ["AAA", "BBB"])
        self.assertEqual(matrix.loc[pd.Timestamp("2026-01-03"), "AAA"], 11.0)
        self.assertEqual(errors, [])

    @patch("investing.core.clustering.query_stock_histories")
    def test_missing_stored_history_is_reported_without_fetching(
        self, query_histories
    ) -> None:
        query_histories.return_value = pd.DataFrame(
            [
                {"date": "2026-01-02", "symbol": "AAA", "country": "norway", "close": 10.0},
            ]
        )

        matrix, errors = build_close_price_matrix(
            ["AAA", "MISSING"],
            {"AAA": "norway", "MISSING": "canada"},
            days=365,
        )

        self.assertEqual(list(matrix.columns), ["AAA"])
        self.assertEqual(errors[0]["symbol"], "MISSING")
        self.assertIn("No stored price history", errors[0]["error"])


class ClusterRelationshipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.correlation = pd.DataFrame(
            [
                [1.0, 0.8, 0.4, -0.2],
                [0.8, 1.0, 0.2, -0.4],
                [0.4, 0.2, 1.0, 0.1],
                [-0.2, -0.4, 0.1, 1.0],
            ],
            index=["AAA", "AAB", "BBB", "CCC"],
            columns=["AAA", "AAB", "BBB", "CCC"],
        )
        self.clusters = pd.DataFrame(
            [
                {"cluster": 1, "symbol": "AAA"},
                {"cluster": 1, "symbol": "AAB"},
                {"cluster": 2, "symbol": "BBB"},
                {"cluster": 3, "symbol": "CCC"},
            ]
        )

    def test_distance_is_one_minus_average_cross_cluster_correlation(self) -> None:
        distances = cluster_distance_matrix(self.correlation, self.clusters)

        self.assertAlmostEqual(distances.loc[1, 2], 0.7)
        self.assertAlmostEqual(distances.loc[1, 3], 1.3)
        self.assertAlmostEqual(distances.loc[2, 3], 0.9)

    def test_layout_supports_rotatable_three_dimensional_view(self) -> None:
        distances = cluster_distance_matrix(self.correlation, self.clusters)

        layout_2d = cluster_network_layout(distances, dimensions=2)
        layout_3d = cluster_network_layout(distances, dimensions=3)

        self.assertEqual(list(layout_2d.columns), ["cluster", "x", "y", "z"])
        self.assertEqual(list(layout_3d.columns), ["cluster", "x", "y", "z"])
        self.assertEqual(len(layout_3d), 3)

    def test_summary_reports_nearest_farthest_and_metadata_interpretation(self) -> None:
        metadata = pd.DataFrame(
            [
                {"symbol": "AAA", "sector": "Energy", "country": "norway"},
                {"symbol": "AAB", "sector": "Energy", "country": "norway"},
                {"symbol": "BBB", "sector": "Technology", "country": "sweden"},
                {"symbol": "CCC", "sector": "Utilities", "country": "canada"},
            ]
        )

        summary = cluster_relationship_summary(
            self.correlation,
            self.clusters,
            metadata,
        )
        cluster_one = summary.loc[summary["cluster"] == "Cluster 1"].iloc[0]

        self.assertEqual(cluster_one["nearest_cluster"], "Cluster 2")
        self.assertEqual(cluster_one["farthest_cluster"], "Cluster 3")
        self.assertEqual(cluster_one["dominant_sector"], "Energy (100%)")
        self.assertIn("correlation alone does not establish", cluster_one["interpretation"])

    def test_graph_links_keep_closest_connections(self) -> None:
        distances = cluster_distance_matrix(self.correlation, self.clusters)

        edges = nearest_cluster_edges(distances, links_per_cluster=1)
        connected_pairs = {
            frozenset((row.cluster_a, row.cluster_b))
            for row in edges.itertuples(index=False)
        }

        self.assertIn(frozenset((1, 2)), connected_pairs)
        self.assertIn(frozenset((2, 3)), connected_pairs)

    def test_default_clustering_caps_excessive_group_count(self) -> None:
        symbols = [f"S{index:03d}" for index in range(40)]
        correlation = pd.DataFrame(
            0.0,
            index=symbols,
            columns=symbols,
        )
        for symbol in symbols:
            correlation.loc[symbol, symbol] = 1.0

        clusters = cluster_by_correlation(
            correlation,
            min_correlation=0.65,
        )

        self.assertEqual(clusters["cluster"].nunique(), 12)
        self.assertEqual(set(clusters["symbol"]), set(symbols))

    def test_cluster_cap_merges_the_most_similar_groups_first(self) -> None:
        correlation = self.correlation.copy()

        clusters = cluster_by_correlation(
            correlation,
            min_correlation=0.95,
            max_clusters=2,
        )
        cluster_by_symbol = clusters.set_index("symbol")["cluster"].to_dict()

        self.assertEqual(cluster_by_symbol["AAA"], cluster_by_symbol["AAB"])
        self.assertEqual(clusters["cluster"].nunique(), 2)

    def test_cluster_cap_can_be_disabled(self) -> None:
        clusters = cluster_by_correlation(
            self.correlation,
            min_correlation=0.95,
            max_clusters=None,
        )

        self.assertEqual(clusters["cluster"].nunique(), 4)

    def test_similarity_prioritizes_same_and_opposite_return_movement(self) -> None:
        dates = pd.date_range("2026-01-01", periods=7)
        returns = np.asarray([0.01, 0.02, -0.01, 0.03, -0.02, 0.01])
        prices = pd.DataFrame(
            {
                "AAA": np.r_[100, 100 * (1 + returns).cumprod()],
                "AAB": np.r_[80, 80 * (1 + returns).cumprod()],
                "CCC": np.r_[120, 120 * (1 - returns).cumprod()],
            },
            index=dates,
        )
        metadata = pd.DataFrame(
            [
                {"symbol": "AAA", "pe_ratio": 12, "dividend_payer": True},
                {"symbol": "AAB", "pe_ratio": 13, "dividend_payer": True},
                {"symbol": "CCC", "pe_ratio": 40, "dividend_payer": False},
            ]
        )

        components = build_stock_similarity(
            prices,
            metadata,
            fundamental_weight=0.25,
        )

        self.assertGreater(
            components["return_correlation"].loc["AAA", "AAB"],
            0.99,
        )
        self.assertLess(
            components["return_correlation"].loc["AAA", "CCC"],
            -0.9,
        )
        self.assertGreater(
            components["similarity"].loc["AAA", "AAB"],
            components["similarity"].loc["AAA", "CCC"],
        )

    def test_fundamental_similarity_uses_dividends_and_essential_factors(self) -> None:
        prices = pd.DataFrame(
            {
                "AAA": [100, 101, 102, 103],
                "AAB": [90, 91, 92, 93],
                "CCC": [80, 81, 82, 83],
            }
        )
        metadata = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "pe_ratio": 12,
                    "return_on_equity": 0.18,
                    "debt_to_equity": 0.4,
                    "dividend_yield": 0.04,
                    "dividend_payer": True,
                },
                {
                    "symbol": "AAB",
                    "pe_ratio": 13,
                    "return_on_equity": 0.17,
                    "debt_to_equity": 0.5,
                    "dividend_yield": 0.035,
                    "dividend_payer": True,
                },
                {
                    "symbol": "CCC",
                    "pe_ratio": 45,
                    "return_on_equity": 0.02,
                    "debt_to_equity": 2.5,
                    "dividend_yield": 0.0,
                    "dividend_payer": False,
                },
            ]
        )

        fundamentals = build_stock_similarity(
            prices,
            metadata,
            fundamental_weight=0.5,
        )["fundamental_similarity"]

        self.assertGreater(
            fundamentals.loc["AAA", "AAB"],
            fundamentals.loc["AAA", "CCC"],
        )


if __name__ == "__main__":
    unittest.main()
