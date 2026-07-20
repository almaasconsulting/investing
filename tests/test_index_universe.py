from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from investing.data_fetch.index_universe import (
    ConstituentSource,
    EURONEXT_OSEBX_COMPOSITION_URL,
    INVESTING_OSEBX_COMPONENTS_URL,
    InvestingIndexEntry,
    MAJOR_INDEXES_BY_COUNTRY,
    STOCK_UNIVERSE_COLUMNS,
    _fetch_investing_index_components,
    _constituent_csv,
    _index_rows,
    _parse_investing_index_catalog,
    fetch_curated_index_universe,
    fetch_flagship_index_universe,
)


class IndexUniverseTests(unittest.TestCase):
    def setUp(self) -> None:
        empty_catalog = pd.DataFrame(columns=STOCK_UNIVERSE_COLUMNS)
        empty_catalog.attrs["warnings"] = []
        patcher = patch(
            "investing.data_fetch.index_universe.fetch_investing_index_catalog_universe",
            return_value=empty_catalog,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_investing_europe_catalog_keeps_only_selected_countries(self) -> None:
        html = """
        <table>
          <tr><td><span title="Germany"></span></td>
              <td><a href="/indices/germany-30">DAX</a></td></tr>
          <tr><td><span title="France"></span></td>
              <td><a href="/indices/france-40">CAC 40</a></td></tr>
          <tr><td><span title="Belgium"></span></td>
              <td><a href="/indices/bel-20">BEL 20</a></td></tr>
        </table>
        """
        result = _parse_investing_index_catalog(
            html,
            allowed_countries={"germany", "france"},
        )

        self.assertEqual([entry.name for entry in result], ["DAX", "CAC 40"])
        self.assertEqual(
            result[0].components_url,
            "https://www.investing.com/indices/germany-30-components",
        )

    def test_investing_component_rows_resolve_to_packaged_stock_symbols(self) -> None:
        entry = InvestingIndexEntry(
            "S&P 500",
            "united states",
            "https://www.investing.com/indices/us-spx-500-components",
        )
        reference = pd.DataFrame([
            {
                "id": "6408", "tag": "apple-computer-inc", "name": "Apple",
                "full_name": "Apple Inc", "symbol": "AAPL", "country": "united states",
                "isin": "US0378331005", "currency": "USD",
            }
        ])
        html = """
        <table><tr id="pair_6408"><td>
          <a href="/equities/apple-computer-inc">Apple</a>
        </td></tr></table>
        """
        with patch(
            "investing.data_fetch.index_universe._download_text", return_value=html
        ):
            result = _fetch_investing_index_components(entry, reference)

        self.assertEqual(result["symbol"].tolist(), ["AAPL"])
        self.assertEqual(result["market"].tolist(), ["S&P 500"])
        self.assertEqual(result["source"].tolist(), ["investing_index_component"])

    def test_norway_uses_full_ose_benchmark_sources(self) -> None:
        self.assertTrue(INVESTING_OSEBX_COMPONENTS_URL.endswith("ose-benchamrk-components"))
        self.assertEqual(
            MAJOR_INDEXES_BY_COUNTRY["norway"][0].url,
            EURONEXT_OSEBX_COMPOSITION_URL,
        )

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

    def test_holdings_csv_skips_preamble_and_non_equity_rows(self) -> None:
        payload = """Fund Holdings as of,2026-07-20
Issuer Ticker,Name,Sector,Asset Class
AAA,Alpha,Technology,Equity
USD,USD Cash,Cash,Cash
BBB,Beta,Industrials,Equity
"""
        frame, symbol_column, name_column = _constituent_csv(payload, 2)
        self.assertEqual(frame[symbol_column].tolist(), ["AAA", "BBB"])
        self.assertEqual(name_column, "Name")

    def test_major_index_sources_are_combined_and_deduplicated(self) -> None:
        def source_frame(source: ConstituentSource, _country: str) -> pd.DataFrame:
            symbols = ["OVERLAP", source.name.upper().replace(" ", "-")]
            rows = []
            for symbol in symbols:
                rows.append({
                    "symbol": symbol, "yahoo_symbol": symbol, "name": symbol,
                    "full_name": symbol, "country": "united states",
                    "market": source.name, "exchange": "NYSE / Nasdaq",
                    "exchange_mic": "", "isin": "", "currency": "USD",
                    "source": "test", "source_url": source.url, "is_active": True,
                    "refreshed_at": pd.Timestamp("2026-07-20"),
                })
            return pd.DataFrame(rows, columns=STOCK_UNIVERSE_COLUMNS)

        with patch(
            "investing.data_fetch.index_universe._index_rows", side_effect=source_frame
        ) as index_rows:
            result = fetch_flagship_index_universe("united states")

        self.assertEqual(index_rows.call_count, 3)
        self.assertEqual(result["yahoo_symbol"].tolist().count("OVERLAP"), 1)
        self.assertEqual(set(result["market"]), {"S&P 500", "Nasdaq-100", "Russell 2000"})

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
