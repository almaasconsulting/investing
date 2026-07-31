from __future__ import annotations

import unittest

import pandas as pd

from investing.core.news_sentiment import score_news_text, summarize_stock_news


class NewsSentimentTests(unittest.TestCase):
    def test_finance_language_is_classified_transparently(self) -> None:
        positive = score_news_text(
            "Company beats estimates, raises guidance and announces a buyback"
        )
        negative = score_news_text(
            "Company issues profit warning after weak demand and losses"
        )

        self.assertEqual(positive["label"], "Positive")
        self.assertGreater(positive["score"], 0)
        self.assertEqual(negative["label"], "Negative")
        self.assertLess(negative["score"], 0)
        self.assertIn("profit warning", negative["negative_hits"])
        self.assertNotIn("profit", negative["positive_hits"])

    def test_recommendations_receive_news_coverage_and_unavailable_status(self) -> None:
        stocks = pd.DataFrame(
            [
                {"symbol": "AAA", "country": "norway"},
                {"symbol": "NONE", "country": "sweden"},
            ]
        )
        news = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "country": "norway",
                    "title": "AAA beats estimates",
                    "summary": "Strong demand and growth",
                    "published_at": "2026-07-20",
                    "url": "https://example.com/positive",
                },
                {
                    "symbol": "AAA",
                    "country": "norway",
                    "title": "AAA announces expansion",
                    "summary": "",
                    "published_at": "2026-07-19",
                    "url": "https://example.com/expansion",
                },
            ]
        )

        enriched = summarize_stock_news(news, stocks).set_index("symbol")

        self.assertEqual(enriched.loc["AAA", "news_sentiment"], "Positive")
        self.assertEqual(enriched.loc["AAA", "news_articles"], 2)
        self.assertEqual(enriched.loc["AAA", "positive_articles"], 2)
        self.assertEqual(
            enriched.loc["AAA", "latest_news_title"],
            "AAA beats estimates",
        )
        self.assertEqual(enriched.loc["NONE", "news_sentiment"], "Unavailable")


if __name__ == "__main__":
    unittest.main()
