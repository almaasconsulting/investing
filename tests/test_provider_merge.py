from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import pandas as pd

from investing.core.stock_analysis import (
    _get_yahoo_dividend_metrics,
    compute_dividend_history_metrics,
    merge_fundamentals,
)
from investing.data_fetch.investing_com import get_stock_data, merge_stock_histories


def history(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])


class ProviderMergeTests(unittest.TestCase):
    def test_yahoo_dividends_fall_back_from_max_to_short_periods(self) -> None:
        ticker = Mock()
        ticker.history.side_effect = [
            ValueError("max is unsupported"),
            pd.DataFrame(),
            pd.DataFrame(
                {"Dividends": [0.25]},
                index=pd.to_datetime(["2026-07-18"]),
            ),
        ]

        metrics = _get_yahoo_dividend_metrics(ticker)

        self.assertEqual(metrics["dividend_years_paid"], 1)
        self.assertEqual(
            [call.kwargs["period"] for call in ticker.history.call_args_list],
            ["max", "5d", "1d"],
        )
        self.assertTrue(
            all(call.kwargs["raise_errors"] for call in ticker.history.call_args_list)
        )

    def test_dividend_history_counts_years_and_growth(self) -> None:
        dividends = pd.Series(
            [1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6],
            index=pd.to_datetime(
                [
                    "2019-06-01",
                    "2020-06-01",
                    "2021-06-01",
                    "2022-06-01",
                    "2023-06-01",
                    "2024-06-01",
                    "2025-06-01",
                ]
            ),
        )

        metrics = compute_dividend_history_metrics(dividends)

        self.assertEqual(metrics["dividend_years_paid"], 7)
        self.assertEqual(metrics["consecutive_dividend_years"], 7)
        self.assertEqual(metrics["latest_dividend_year"], 2025)
        self.assertGreater(metrics["dividend_cagr_5y"], 0)

    def test_fundamentals_prefer_yahoo_and_fill_its_gaps(self) -> None:
        merged = merge_fundamentals(
            {"pe_ratio": 15.0, "beta": None, "sector": "Energy"},
            {"pe_ratio": "17.5", "beta": 0.8, "revenue": 1000},
        )

        self.assertEqual(merged["pe_ratio"], 15.0)
        self.assertEqual(merged["beta"], 0.8)
        self.assertEqual(merged["revenue"], 1000)
        self.assertEqual(merged["field_sources"]["pe_ratio"], "yahoo")
        self.assertEqual(merged["field_sources"]["beta"], "investing")
        self.assertEqual(merged["providers_used"], ["yahoo", "investing"])

    def test_price_history_prefers_yahoo_by_date_and_field(self) -> None:
        yahoo = history(
            [
                ("2026-01-02", 10, 12, 9, 11, None),
                ("2026-01-05", 11, 13, 10, 12, 100),
            ]
        )
        investing = history(
            [
                ("2026-01-02", 20, 22, 19, 21, 200),
                ("2026-01-03", 30, 32, 29, 31, 300),
            ]
        )

        merged = merge_stock_histories(yahoo, investing).set_index("date")
        self.assertEqual(merged.loc[pd.Timestamp("2026-01-02"), "close"], 11)
        self.assertEqual(merged.loc[pd.Timestamp("2026-01-02"), "volume"], 200)
        self.assertEqual(merged.loc[pd.Timestamp("2026-01-02"), "price_source"], "yahoo+investing")
        self.assertEqual(merged.loc[pd.Timestamp("2026-01-03"), "close"], 31)
        self.assertEqual(merged.loc[pd.Timestamp("2026-01-03"), "price_source"], "investing")

    @patch("investing.data_fetch.investing_com._get_stock_data_investing")
    @patch("investing.data_fetch.investing_com._get_stock_data_yahoo")
    def test_auto_queries_both_providers(self, yahoo_fetch, investing_fetch) -> None:
        yahoo_fetch.return_value = history([("2026-01-02", 10, 12, 9, 11, 100)])
        investing_fetch.return_value = history([("2026-01-03", 20, 22, 19, 21, 200)])

        merged = get_stock_data("TEST", source="auto")

        yahoo_fetch.assert_called_once()
        investing_fetch.assert_called_once()
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged.attrs["providers_used"], ["yahoo", "investing"])

    @patch("investing.data_fetch.investing_com._get_stock_data_investing")
    @patch("investing.data_fetch.investing_com._get_stock_data_yahoo")
    def test_auto_continues_when_one_provider_fails(self, yahoo_fetch, investing_fetch) -> None:
        yahoo_fetch.side_effect = ValueError("Yahoo unavailable")
        investing_fetch.return_value = history([("2026-01-02", 20, 22, 19, 21, 200)])

        result = get_stock_data("TEST", source="auto")

        self.assertEqual(result.iloc[0]["close"], 21)
        self.assertEqual(result.attrs["data_source"], "investing")
        self.assertEqual(result.attrs["providers_used"], ["investing"])


if __name__ == "__main__":
    unittest.main()
