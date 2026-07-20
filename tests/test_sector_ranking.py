from __future__ import annotations

import unittest

import pandas as pd

from investing.core.ranking import (
    SECTOR_FUNDAMENTAL_PROFILES,
    SECTOR_DIVIDEND_WEIGHTS,
    build_dividend_quality_score,
    build_rankings,
    build_sector_fundamental_score,
    normalize_sector,
    top_stocks_by_country_sector,
)


class SectorFundamentalScoreTests(unittest.TestCase):
    def test_all_profile_weights_sum_to_one(self) -> None:
        for sector, profile in SECTOR_FUNDAMENTAL_PROFILES.items():
            with self.subTest(sector=sector):
                self.assertAlmostEqual(sum(profile.values()), 1.0)
                self.assertGreaterEqual(SECTOR_DIVIDEND_WEIGHTS[sector], 0.0)
                self.assertLessEqual(SECTOR_DIVIDEND_WEIGHTS[sector], 1.0)

    def test_dividend_yield_is_scored_relative_to_sector(self) -> None:
        fundamentals = {
            "dividend_yield": 0.02,
            "consecutive_dividend_years": 5,
            "dividend_cagr_5y": 0.05,
            "payout_ratio": 0.50,
        }
        technology = build_dividend_quality_score(fundamentals, "Technology")
        utilities = build_dividend_quality_score(fundamentals, "Utilities")
        self.assertGreater(technology["score"], utilities["score"])

    def test_long_dividend_history_improves_quality_score(self) -> None:
        base = {
            "dividend_yield": 0.04,
            "dividend_cagr_5y": 0.05,
            "payout_ratio": 0.50,
        }
        new_payer = build_dividend_quality_score(
            {**base, "consecutive_dividend_years": 1}, "Consumer Defensive"
        )
        established = build_dividend_quality_score(
            {**base, "consecutive_dividend_years": 10}, "Consumer Defensive"
        )
        self.assertGreater(established["score"], new_payer["score"])

    def test_yahoo_and_gics_sector_names_are_normalized(self) -> None:
        self.assertEqual(normalize_sector("Financials"), "Financial Services")
        self.assertEqual(normalize_sector("Consumer Discretionary"), "Consumer Cyclical")
        self.assertEqual(normalize_sector("Information Technology"), "Technology")
        self.assertEqual(normalize_sector(None), "Diversified")

    def test_financials_prioritize_roe_roa_and_price_to_book(self) -> None:
        score = build_sector_fundamental_score(
            {
                "sector": "Financial Services",
                "pe_ratio": 12,
                "price_to_book": 1.2,
                "return_on_equity": 0.22,
                "return_on_assets": 0.025,
                "earnings_growth": 0.12,
                "dividend_yield": 0.03,
                "payout_ratio": 0.45,
                "debt_to_equity": 500,
                "altman_z_score": 0.5,
            }
        )
        self.assertEqual(score["sector_profile"], "Financial Services")
        self.assertEqual(score["fundamental_coverage"], 93.4)
        self.assertNotIn("debt_to_equity", score["component_scores"])
        self.assertNotIn("altman_z_score", score["component_scores"])
        self.assertGreater(score["fundamental_score"], 70)

    def test_missing_data_is_neutral_and_reduces_coverage(self) -> None:
        score = build_sector_fundamental_score({"sector": "Technology", "revenue_growth": 0.25})
        self.assertEqual(score["fundamental_coverage"], 19.0)
        self.assertGreater(score["fundamental_score"], 50.0)
        self.assertLess(score["fundamental_score"], 65.0)

    def test_rankings_include_rank_within_sector(self) -> None:
        def result(symbol: str, growth: float) -> dict:
            return {
                "symbol": symbol,
                "scorecard": {"score": 0.02, "price_change": 0.1, "volatility": 0.03},
                "technical": {"rsi": 55, "direction": "neutral"},
                "fundamentals": {"sector": "Technology", "revenue_growth": growth},
            }

        rankings = build_rankings(
            [result("FAST", 0.25), result("SLOW", -0.05)],
            technical_weight=0.0,
            group_by="sector",
        )
        ranked = rankings.set_index("symbol")
        self.assertEqual(ranked.loc["FAST", "sector_rank"], 1)
        self.assertEqual(ranked.loc["SLOW", "sector_rank"], 2)
        self.assertGreater(ranked.loc["FAST", "fundamental_score"], ranked.loc["SLOW", "fundamental_score"])

    def test_top_stocks_are_ranked_within_each_country_and_sector(self) -> None:
        rankings = pd.DataFrame(
            [
                {"symbol": f"NO{i}", "country": "norway", "sector": "Energy", "ranking_score": 100 - i}
                for i in range(1, 8)
            ]
            + [
                {"symbol": "US1", "country": "united states", "sector": "Energy", "ranking_score": 75},
                {"symbol": "NO-T", "country": "norway", "sector": "Technology", "ranking_score": 70},
            ]
        )

        top = top_stocks_by_country_sector(rankings, limit=5)

        norway_energy = top[(top["country"] == "norway") & (top["sector"] == "Energy")]
        self.assertEqual(norway_energy["symbol"].tolist(), ["NO1", "NO2", "NO3", "NO4", "NO5"])
        self.assertEqual(norway_energy["country_sector_rank"].tolist(), [1, 2, 3, 4, 5])
        self.assertIn("US1", top["symbol"].tolist())
        self.assertIn("NO-T", top["symbol"].tolist())


if __name__ == "__main__":
    unittest.main()
