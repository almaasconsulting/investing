from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from investing.data_fetch.stock_universe import STOCK_UNIVERSE_COLUMNS, fetch_stock_universe


def _row(country: str, symbol: str, market: str) -> pd.DataFrame:
    return pd.DataFrame([{
        "symbol": symbol, "yahoo_symbol": symbol, "name": symbol, "full_name": symbol,
        "country": country, "market": market, "exchange": market, "exchange_mic": "",
        "isin": "", "currency": "NOK" if country == "norway" else "USD",
        "source": "test", "source_url": "https://example.test", "is_active": True,
        "refreshed_at": pd.Timestamp("2026-07-20"),
    }], columns=STOCK_UNIVERSE_COLUMNS)


class UniversePolicyTests(unittest.TestCase):
    def test_norway_uses_full_exchange_and_other_countries_use_indexes(self) -> None:
        norway = _row("norway", "EQNR.OL", "Oslo Bors")
        indexed = pd.concat([
            _row("united states", "MSFT", "S&P 500"),
            _row("canada", "RY.TO", "S&P/TSX 60"),
        ], ignore_index=True)
        with (
            patch("investing.data_fetch.stock_universe.fetch_norway_stock_universe", return_value=norway) as norway_fetch,
            patch("investing.data_fetch.stock_universe.fetch_curated_index_universe", return_value=indexed) as index_fetch,
        ):
            result = fetch_stock_universe(["norway", "united states", "canada"])

        norway_fetch.assert_called_once_with()
        index_fetch.assert_called_once_with(["united states", "canada"])
        self.assertEqual(set(result["country"]), {"norway", "united states", "canada"})


if __name__ == "__main__":
    unittest.main()
