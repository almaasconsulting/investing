from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from investing.pipeline.config import PipelineSettings
from investing.pipeline.updates import analyze_universe_frame, run_universe_update


class ParallelPipelineTests(unittest.TestCase):
    def test_automated_update_enforces_age_but_manual_can_override(self) -> None:
        settings = PipelineSettings(
            watchlist_path=Path("watchlist.csv"), countries=("canada",)
        )
        empty_queue = pd.DataFrame(columns=["symbol", "country"])
        with (
            patch(
                "investing.pipeline.updates.query_stock_analysis_queue",
                return_value=empty_queue,
            ) as queue,
            patch("investing.pipeline.updates._reserve_updates"),
            patch("investing.pipeline.updates.analyze_universe_frame", return_value=[]),
            patch(
                "investing.pipeline.updates.persist_analysis_results",
                return_value={
                    "price_histories": 0,
                    "fundamental_snapshots": 0,
                    "analysis_snapshots": 0,
                },
            ),
        ):
            run_universe_update(settings)
            self.assertEqual(
                queue.call_args.kwargs["minimum_success_age_hours"], 24.0
            )

            run_universe_update(settings, force_update=True)
            self.assertIsNone(
                queue.call_args.kwargs["minimum_success_age_hours"]
            )

    def test_analysis_fetches_concurrently_and_preserves_queue_order(self) -> None:
        active = 0
        peak_active = 0
        guard = threading.Lock()

        def analyze(symbols, **kwargs):
            nonlocal active, peak_active
            with guard:
                active += 1
                peak_active = max(peak_active, active)
            time.sleep(0.04)
            with guard:
                active -= 1
            symbol = symbols[0]
            return [{
                "symbol": symbol,
                "country": "canada",
                "ingested_data": pd.DataFrame({"date": ["2026-07-18"]}),
                "fundamentals": {},
            }]

        universe = pd.DataFrame({
            "symbol": [f"S{index}" for index in range(8)],
            "country": ["canada"] * 8,
            "name": [f"Stock {index}" for index in range(8)],
        })
        with tempfile.TemporaryDirectory() as directory:
            settings = PipelineSettings(
                watchlist_path=Path(directory) / "watchlist.csv",
                fetch_workers=4,
            )
            with (
                patch("investing.pipeline.updates.query_stock_history", return_value=pd.DataFrame()),
                patch("investing.pipeline.updates.analyze_stocks", side_effect=analyze),
            ):
                results = analyze_universe_frame(
                    universe, days=30, min_score=0.01, max_volatility=0.06,
                    data_source="auto", settings=settings,
                )

        self.assertGreater(peak_active, 1)
        self.assertLessEqual(peak_active, 4)
        self.assertEqual(
            [result["symbol"] for result in results], universe["symbol"].tolist()
        )


if __name__ == "__main__":
    unittest.main()
