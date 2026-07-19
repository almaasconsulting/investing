from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from investing.db.postgres_compat import _postgres_sql
from investing.db.postgres_store import _to_json
from investing.db.store import (
    get_database_url,
    query_stock_analysis_queue,
    save_fundamental_snapshot,
    save_stock_history,
)
from investing.pipeline.config import PipelineSettings


class PostgreSQLConfigurationTests(unittest.TestCase):
    def test_analysis_queue_requires_24_hours_since_last_success(self) -> None:
        with patch(
            "investing.db.postgres_store._fetch_frame",
            return_value=pd.DataFrame(),
        ) as fetch:
            query_stock_analysis_queue("canada")

        sql, params, _db_path = fetch.call_args.args
        self.assertIn("s.last_succeeded_at <= CURRENT_TIMESTAMP", sql)
        self.assertIn("INTERVAL '1 hour'", sql)
        self.assertIn(24.0, params)

    def test_discrete_parameters_build_encoded_connection_url(self) -> None:
        environment = {
            "INVESTING_DATABASE_URL": "",
            "INVESTING_POSTGRES_HOST": "db.internal",
            "INVESTING_POSTGRES_PORT": "5433",
            "INVESTING_POSTGRES_DATABASE": "market data",
            "INVESTING_POSTGRES_USER": "analysis user",
            "INVESTING_POSTGRES_PASSWORD": "p@ss/word",
            "INVESTING_POSTGRES_SSLMODE": "require",
            "INVESTING_BATCH_SIZE": "300",
        }
        with patch.dict(os.environ, environment, clear=False):
            self.assertEqual(
                get_database_url(),
                "postgresql://analysis%20user:p%40ss%2Fword@db.internal:5433/"
                "market%20data?sslmode=require",
            )
            settings = PipelineSettings.from_env()
            self.assertEqual(settings.postgres_host, "db.internal")
            self.assertEqual(settings.postgres_port, 5433)
            self.assertEqual(settings.batch_size, 300)
            self.assertNotIn("p@ss/word", repr(settings))

    def test_parameter_placeholders_and_double_are_translated(self) -> None:
        self.assertEqual(
            _postgres_sql("select cast(? as DOUBLE), cast(? as DOUBLE PRECISION)"),
            "select cast(%s as DOUBLE PRECISION), cast(%s as DOUBLE PRECISION)",
        )

    def test_stock_history_coerces_missing_provider_prices_to_numeric(self) -> None:
        connection = MagicMock()
        registered: dict[str, pd.DataFrame] = {}
        connection.register.side_effect = (
            lambda name, frame: registered.setdefault(name, frame.copy())
        )
        history = pd.DataFrame(
            {
                "date": ["2026-07-18"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.0],
                "close": [10.5],
                "volume": [1000],
            }
        )

        with patch("investing.db.postgres_store.init_db", return_value=connection):
            save_stock_history(history, "TEST", "Test", "italy")

        staged = registered["new_data"]
        self.assertTrue(pd.api.types.is_numeric_dtype(staged["yahoo_open"]))
        self.assertTrue(pd.api.types.is_numeric_dtype(staged["investing_open"]))
        insert_sql = connection.execute.call_args.args[0]
        self.assertIn("CAST(yahoo_open AS DOUBLE PRECISION)", insert_sql)
        self.assertIn("CAST(volume AS BIGINT)", insert_sql)
        connection.unregister.assert_called_once_with("new_data")
        connection.close.assert_called_once()

    def test_fundamentals_use_destination_types_when_values_are_missing(self) -> None:
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = None
        registered: dict[str, pd.DataFrame] = {}

        def capture(name, frame, **kwargs):
            registered[name] = frame.copy()

        connection.register.side_effect = capture

        with patch("investing.db.postgres_store.init_db", return_value=connection):
            saved = save_fundamental_snapshot({}, "TEST", "Test", "italy")

        self.assertTrue(saved)
        staged = registered["new_data"]
        self.assertTrue(pd.api.types.is_numeric_dtype(staged["market_cap"]))
        register_kwargs = connection.register.call_args.kwargs
        self.assertEqual(
            register_kwargs["column_types"]["market_cap"], "DOUBLE PRECISION"
        )
        self.assertEqual(
            register_kwargs["column_types"]["latest_dividend_year"], "INTEGER"
        )
        insert_sql = connection.execute.call_args.args[0]
        self.assertIn("CAST(peg_ratio AS DOUBLE PRECISION)", insert_sql)
        self.assertIn("CAST(latest_dividend_year AS INTEGER)", insert_sql)

    def test_json_serialization_replaces_non_finite_numbers_with_null(self) -> None:
        payload = _to_json(
            {
                "nan": float("nan"),
                "positive": float("inf"),
                "nested": [1.0, pd.NA],
            }
        )

        self.assertNotIn("NaN", payload)
        self.assertNotIn("Infinity", payload)
        self.assertEqual(
            payload,
            '{"nan": null, "nested": [1.0, null], "positive": null}',
        )


if __name__ == "__main__":
    unittest.main()
