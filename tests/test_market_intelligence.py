from __future__ import annotations

import unittest
import os
import tempfile
import warnings
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from investing.data_fetch.market_intelligence import (
    _investing_statement_value,
    canonical_line_item,
    fetch_financial_statements,
    fetch_stock_news,
)
from investing.data_fetch.investpy_compat import _import_investpy, load_investpy
from investing.data_fetch.stock_universe import (
    DEFAULT_MARKET_COUNTRIES,
    fetch_yahoo_exchange_stock_universe,
)
from investing.db.store import (
    init_db,
    query_stock_analysis_queue,
    query_stock_content_queue,
)


class MarketIntelligenceTests(unittest.TestCase):
    def test_investpy_pkg_resources_warning_is_suppressed(self) -> None:
        def warned_import(_module_name):
            warnings.warn("pkg_resources is deprecated as an API.", UserWarning)
            return object()

        with patch(
            "investing.data_fetch.investpy_compat.importlib.import_module",
            side_effect=warned_import,
        ), warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _import_investpy()

        self.assertEqual(caught, [])

    def test_investpy_loads_without_pkg_resources_dependency(self) -> None:
        investpy = load_investpy()
        self.assertTrue(callable(investpy.get_stock_financial_summary))

    def test_investing_statement_amounts_are_converted_from_millions(self) -> None:
        self.assertEqual(_investing_statement_value("Total Revenue", 125.5), 125_500_000.0)
        self.assertEqual(_investing_statement_value("Diluted EPS", 2.5), 2.5)

    def test_default_catalog_includes_requested_markets(self) -> None:
        self.assertEqual(len(DEFAULT_MARKET_COUNTRIES), 13)
        self.assertIn("united states", DEFAULT_MARKET_COUNTRIES)
        self.assertIn("canada", DEFAULT_MARKET_COUNTRIES)

    @patch("investing.data_fetch.stock_universe.yf.screen")
    def test_exchange_universe_keeps_yahoo_symbol_and_mic(self, screen) -> None:
        screen.return_value = {
            "total": 1,
            "quotes": [{
                "symbol": "SHOP.TO", "quoteType": "EQUITY", "exchange": "TOR",
                "shortName": "Shopify", "longName": "Shopify Inc.", "currency": "CAD",
            }],
        }
        frame = fetch_yahoo_exchange_stock_universe("canada")
        self.assertEqual(frame.iloc[0]["symbol"], "SHOP")
        self.assertEqual(frame.iloc[0]["yahoo_symbol"], "SHOP.TO")
        self.assertEqual(frame.iloc[0]["exchange_mic"], "XTSE")

    def test_line_items_are_normalized_across_providers(self) -> None:
        self.assertEqual(canonical_line_item("Total Revenue"), "revenue")
        self.assertEqual(canonical_line_item("TotalRevenue"), "revenue")
        self.assertEqual(canonical_line_item("Net Income Common Stockholders"), "net_income")

    @patch("investing.data_fetch.market_intelligence._investing_statement_rows")
    @patch("investing.data_fetch.market_intelligence._yahoo_statement_rows")
    def test_auto_retains_both_statement_providers(self, yahoo_rows, investing_rows) -> None:
        yahoo_rows.return_value = [{"provider": "yahoo", "value": 10.0}]
        investing_rows.return_value = [{"provider": "investing", "value": 11.0}]

        result = fetch_financial_statements("TEST", source="auto")

        self.assertEqual(result["provider"].tolist(), ["yahoo", "investing"])

    @patch("investing.data_fetch.market_intelligence.yf.Ticker")
    def test_news_normalizes_current_yfinance_payload(self, ticker_class) -> None:
        ticker_class.return_value.get_news.return_value = [
            {
                "content": {
                    "id": "article-1",
                    "title": "Quarterly result",
                    "summary": "Revenue increased.",
                    "pubDate": "2026-07-18T08:00:00Z",
                    "provider": {"displayName": "Example News"},
                    "canonicalUrl": {"url": "https://example.com/article-1"},
                }
            }
        ]

        result = fetch_stock_news("TEST", "united states")

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["publisher"], "Example News")
        self.assertTrue(result.iloc[0]["record_hash"])
        self.assertEqual(result.iloc[0]["yahoo_symbol"], "TEST")

    @unittest.skipUnless(
        os.getenv("INVESTING_TEST_POSTGRES") == "1",
        "requires an isolated PostgreSQL integration database",
    )
    def test_universe_queues_put_never_run_then_oldest_first(self) -> None:
        with tempfile.TemporaryDirectory():
            con = init_db()
            for symbol in ("A", "B", "C"):
                con.execute(
                    "INSERT INTO stock_universe (symbol, country, is_active) VALUES (?, 'canada', true)",
                    [symbol],
                )
            con.execute(
                """
                INSERT INTO stock_update_status
                    (update_type, ticker, country, last_attempted_at)
                VALUES
                    ('analysis', 'A', 'canada', timestamp '2026-01-02'),
                    ('analysis', 'B', 'canada', timestamp '2026-01-01'),
                    ('content', 'A', 'canada', timestamp '2026-01-02'),
                    ('content', 'B', 'canada', timestamp '2026-01-01')
                """
            )
            con.close()

            analysis = query_stock_analysis_queue("canada", limit=3, db_path=db_path)
            content = query_stock_content_queue("canada", limit=3, db_path=db_path)
            self.assertEqual(analysis["symbol"].tolist(), ["C", "B", "A"])
            self.assertEqual(content["symbol"].tolist(), ["C", "B", "A"])


if __name__ == "__main__":
    unittest.main()
