from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from investing.core.cluster_optimizer import optimize_stock_clusters
from investing.core.cluster_report import generate_cluster_report


class ClusterReportTests(unittest.TestCase):
    def test_report_contains_process_charts_and_cluster_tables(self) -> None:
        random = np.random.default_rng(4)
        dates = pd.date_range("2025-01-01", periods=70)
        first = random.normal(0.001, 0.01, len(dates) - 1)
        second = random.normal(-0.001, 0.012, len(dates) - 1)
        prices = {}
        for symbol in ("AAA", "AAB", "AAC"):
            noise = random.normal(0, 0.001, len(first))
            prices[symbol] = np.r_[100, 100 * (1 + first + noise).cumprod()]
        for symbol in ("BBB", "BBC", "BBD"):
            noise = random.normal(0, 0.001, len(second))
            prices[symbol] = np.r_[100, 100 * (1 + second + noise).cumprod()]
        price_frame = pd.DataFrame(prices, index=dates)
        metadata = pd.DataFrame(
            [
                {
                    "symbol": symbol,
                    "name": f"Company {symbol}",
                    "country": "norway",
                    "sector": "Energy" if symbol.startswith("A") else "Finance",
                    "pe_ratio": 10 + index,
                }
                for index, symbol in enumerate(prices)
            ]
        )
        optimization = optimize_stock_clusters(
            price_frame,
            metadata,
            fundamental_weights=[0.0],
            performance_weights=[0.1],
            linkages=["complete"],
        )

        with tempfile.TemporaryDirectory() as directory:
            output = generate_cluster_report(
                optimization,
                metadata,
                {
                    "eligible_stocks": 6,
                    "training_dates": optimization["train_dates"],
                    "validation_dates": optimization["validation_dates"],
                },
                {"min_observations": 45},
                Path(directory) / "cluster-report.html",
            )
            document = output.read_text(encoding="utf-8")

        self.assertIn("Cluster-distance diagrams", document)
        self.assertIn("3D · drag to rotate", document)
        self.assertIn("Parameter-search results", document)
        self.assertIn("Cluster relationships and interpretation", document)
        self.assertIn("Company AAA", document)
        self.assertIn("Plotly.newPlot", document)


if __name__ == "__main__":
    unittest.main()
