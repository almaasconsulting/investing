from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from investing.data_fetch.index_universe import (
    ConstituentSource,
    STOCK_UNIVERSE_COLUMNS,
    _index_rows,
    fetch_curated_index_universe,
)


class IndexUniverseTests(unittest.TestCase):
    def test_constituent_table_normalizes_canadian_class_ticker(self) -> None:
        source = ConstituentSource("Test Index", "https://example.test/index", 2)
        html = """
        <table>
          <tr><th>Company</th><th>Ticker</th></tr>
          <tr><td>Example Inc</td><td>EX.A</td></tr>
          <tr><td>Second Inc</td><td>SECOND</td></tr>
        </table>
        """
        with patch(
            "investing.data_fetch.index_universe._download_text", return_value=html
        ):
            result = _index_rows(source, "canada")

        self.assertEqual(result["symbol"].tolist(), ["EX-A", "SECOND"])
        self.assertEqual(result["yahoo_symbol"].tolist(), ["EX-A.TO", "SECOND.TO"])
        self.assertEqual(result["market"].unique().tolist(), ["Test Index"])

    def test_curated_universe_deduplicates_index_and_extra_memberships(self) -> None:
        def frame(symbols: list[str], country: str, market: str) -> pd.DataFrame:
            rows = []
            for symbol in symbols:
                rows.append(
                    {
                        "symbol": symbol,
                        "yahoo_symbol": symbol if country == "united states" else f"{symbol}.TO",
                        "name": symbol,
                        "full_name": symbol,
                        "country": country,
                        "market": market,
                        "exchange": market,
                        "exchange_mic": "",
                        "isin": "",
                        "currency": "USD" if country == "united states" else "CAD",
                        "source": "test",
                        "source_url": "https://example.test",
                        "is_active": True,
                        "refreshed_at": pd.Timestamp("2026-07-20"),
                    }
                )
            return pd.DataFrame(rows, columns=STOCK_UNIVERSE_COLUMNS)

        with (
            patch(
                "investing.data_fetch.index_universe.fetch_flagship_index_universe",
                return_value=frame(["AAA", "BBB"], "united states", "S&P 500"),
            ),
            patch(
                "investing.data_fetch.index_universe.fetch_reit_universe",
                return_value=frame(["BBB", "REIT"], "united states", "US REITs"),
            ),
            patch(
                "investing.data_fetch.index_universe.fetch_dividend_aristocrats",
                return_value=frame(["AAA", "DIV"], "united states", "US Aristocrats"),
            ),
        ):
            result = fetch_curated_index_universe(["united states"])

        self.assertEqual(result["symbol"].tolist(), ["AAA", "BBB", "REIT", "DIV"])
        self.assertEqual(result.loc[result["symbol"] == "AAA", "market"].iloc[0], "S&P 500")

    def test_optional_enrichment_failure_does_not_fail_flagship_universe(self) -> None:
        flagship = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "yahoo_symbol": "AAA.TO",
                    "name": "AAA",
                    "full_name": "AAA",
                    "country": "canada",
                    "market": "S&P/TSX 60",
                    "exchange": "Toronto Stock Exchange",
                    "exchange_mic": "XTSE",
                    "isin": "",
                    "currency": "CAD",
                    "source": "test",
                    "source_url": "https://example.test",
                    "is_active": True,
                    "refreshed_at": pd.Timestamp("2026-07-20"),
                }
            ],
            columns=STOCK_UNIVERSE_COLUMNS,
        )
        with (
            patch(
                "investing.data_fetch.index_universe.fetch_flagship_index_universe",
                return_value=flagship,
            ),
            patch(
                "investing.data_fetch.index_universe.fetch_reit_universe",
                side_effect=RuntimeError("provider unavailable"),
            ),
            patch(
                "investing.data_fetch.index_universe.fetch_dividend_aristocrats",
                side_effect=RuntimeError("html parser unavailable"),
            ),
        ):
            result = fetch_curated_index_universe(["canada"])

        self.assertEqual(result["symbol"].tolist(), ["AAA"])
        self.assertEqual(len(result.attrs["warnings"]), 2)
        self.assertIn("canada dividend aristocrat enrichment skipped", result.attrs["warnings"][1])

    def test_optional_enrichment_failure_does_not_abort_flagship_refresh(self) -> None:
        flagship = pd.DataFrame(
            [
                {
                    "symbol": "AAA", "yahoo_symbol": "AAA.TO", "name": "AAA",
                    "full_name": "AAA", "country": "canada", "market": "S&P/TSX 60",
                    "exchange": "Toronto Stock Exchange", "exchange_mic": "XTSE",
                    "isin": "", "currency": "CAD", "source": "index_constituent",
                    "source_url": "https://example.test", "is_active": True,
                    "refreshed_at": pd.Timestamp("2026-07-20"),
                }
            ],
            columns=STOCK_UNIVERSE_COLUMNS,
        )
        with (
            patch(
                "investing.data_fetch.index_universe.fetch_flagship_index_universe",
                return_value=flagship,
            ),
            patch(
                "investing.data_fetch.index_universe.fetch_reit_universe",
                side_effect=RuntimeError("Yahoo unavailable"),
            ),
            patch(
                "investing.data_fetch.index_universe.fetch_dividend_aristocrats",
                side_effect=RuntimeError("HTML table unavailable"),
            ),
        ):
            result = fetch_curated_index_universe(["canada"])

        self.assertEqual(result["symbol"].tolist(), ["AAA"])
        self.assertEqual(len(result.attrs["warnings"]), 2)
        self.assertIn("dividend aristocrat enrichment skipped", result.attrs["warnings"][1])


if __name__ == "__main__":
    unittest.main()
