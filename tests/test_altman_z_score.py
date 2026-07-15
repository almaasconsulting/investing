from __future__ import annotations

import math
import unittest

from investing.core.stock_analysis import altman_z_zone, calculate_altman_z_score


class AltmanZScoreTests(unittest.TestCase):
    def test_calculates_original_public_company_formula(self) -> None:
        score = calculate_altman_z_score(
            total_assets=1_000,
            current_assets=500,
            current_liabilities=300,
            retained_earnings=200,
            ebit=100,
            market_value_equity=800,
            total_liabilities=400,
            revenue=1_200,
        )

        self.assertIsNotNone(score)
        self.assertTrue(math.isclose(score, 3.25, rel_tol=1e-12))

    def test_returns_none_for_missing_or_invalid_denominator(self) -> None:
        valid = {
            "total_assets": 1_000,
            "current_assets": 500,
            "current_liabilities": 300,
            "retained_earnings": 200,
            "ebit": 100,
            "market_value_equity": 800,
            "total_liabilities": 400,
            "revenue": 1_200,
        }
        self.assertIsNone(calculate_altman_z_score(**{**valid, "total_assets": 0}))
        self.assertIsNone(calculate_altman_z_score(**{**valid, "total_liabilities": None}))

    def test_classifies_standard_zones(self) -> None:
        self.assertEqual(altman_z_zone(1.80), "Distress")
        self.assertEqual(altman_z_zone(1.81), "Grey")
        self.assertEqual(altman_z_zone(2.99), "Grey")
        self.assertEqual(altman_z_zone(3.0), "Safe")
        self.assertEqual(altman_z_zone(None), "Unavailable")


if __name__ == "__main__":
    unittest.main()
