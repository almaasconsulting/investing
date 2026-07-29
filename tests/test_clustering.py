from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from investing.core.clustering import build_close_price_matrix


class DatabaseClusteringTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
