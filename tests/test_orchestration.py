from __future__ import annotations

import unittest

import dagster as dg

from investing.orchestration.definitions import (
    BATCH_PARTITION_COUNT,
    defs,
)


class NativeDbtAssetTests(unittest.TestCase):
    def test_dbt_models_are_individual_assets(self) -> None:
        graph = defs.resolve_asset_graph()
        asset_keys = {key.to_user_string() for key in graph.get_all_asset_keys()}

        self.assertIn("bronze/bronze_stock_history", asset_keys)
        self.assertIn("silver/silver_stock_price_daily", asset_keys)
        self.assertIn("gold/dim_stock", asset_keys)
        self.assertIn("gold/fact_fundamental_snapshot", asset_keys)
        self.assertIn("bronze/bronze_news_article", asset_keys)
        self.assertIn("silver/silver_financial_statement", asset_keys)
        self.assertIn("gold/fact_fundamental_trend", asset_keys)
        self.assertIn("gold/fact_stock_news", asset_keys)
        self.assertNotIn("silver_and_gold_models", asset_keys)

    def test_bronze_dbt_assets_depend_on_python_ingestion(self) -> None:
        graph = defs.resolve_asset_graph()
        node = graph.get(dg.AssetKey(["bronze", "bronze_stock_history"]))
        parents = {
            parent.key.to_user_string() for parent in graph.get_parents(node)
        }

        self.assertIn("bronze_incremental_market_data", parents)
        self.assertIn("landing/stock_history", parents)
        self.assertEqual(node.group_name, "bronze")

        news_node = graph.get(dg.AssetKey(["bronze", "bronze_news_article"]))
        news_parents = {
            parent.key.to_user_string() for parent in graph.get_parents(news_node)
        }
        self.assertIn("bronze_market_intelligence", news_parents)

        intelligence = graph.get(dg.AssetKey(["bronze", "bronze_financial_statement"]))
        intelligence_parents = {
            parent.key.to_user_string() for parent in graph.get_parents(intelligence)
        }
        self.assertIn("bronze_market_intelligence", intelligence_parents)

    def test_dbt_tests_are_exposed_as_asset_checks(self) -> None:
        graph = defs.resolve_asset_graph()
        self.assertGreaterEqual(len(list(graph.asset_check_keys)), 12)

    def test_ingestion_assets_use_the_same_static_partitions(self) -> None:
        graph = defs.resolve_asset_graph()
        market = graph.get(dg.AssetKey("bronze_incremental_market_data"))
        content = graph.get(dg.AssetKey("bronze_market_intelligence"))

        self.assertIsNotNone(market.partitions_def)
        self.assertEqual(
            market.partitions_def.get_partition_keys(),
            content.partitions_def.get_partition_keys(),
        )
        self.assertEqual(
            len(market.partitions_def.get_partition_keys()), BATCH_PARTITION_COUNT
        )
        content_parents = {
            parent.key.to_user_string() for parent in graph.get_parents(content)
        }
        self.assertIn("bronze_incremental_market_data", content_parents)

    def test_jobs_and_schedules_are_separated(self) -> None:
        for job_name in (
            "universe_refresh_job",
            "stock_batch_refresh_job",
            "medallion_refresh_job",
        ):
            self.assertEqual(defs.get_job_def(job_name).name, job_name)
        for schedule_name in (
            "daily_universe_schedule",
            "continuous_stock_batch_schedule",
            "hourly_medallion_schedule",
        ):
            self.assertEqual(defs.get_schedule_def(schedule_name).name, schedule_name)


if __name__ == "__main__":
    unittest.main()
