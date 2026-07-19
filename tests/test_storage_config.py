from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from investing.db.store import (
    get_database_url,
    get_postgres_schema,
)
from investing.pipeline.config import PipelineSettings


class StorageConfigurationTests(unittest.TestCase):
    def test_postgresql_is_the_only_runtime_backend(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                get_database_url(),
                "postgresql://investing@localhost:5432/investing?sslmode=prefer",
            )

    def test_postgres_url_is_built_from_component_settings(self) -> None:
        environment = {
            "INVESTING_POSTGRES_HOST": "db.internal",
            "INVESTING_POSTGRES_PORT": "5433",
            "INVESTING_POSTGRES_DATABASE": "stock data",
            "INVESTING_POSTGRES_USER": "analysis@example.com",
            "INVESTING_POSTGRES_PASSWORD": "p@ss word",
            "INVESTING_POSTGRES_SSLMODE": "require",
        }
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(
                get_database_url(),
                "postgresql://analysis%40example.com:p%40ss%20word@"
                "db.internal:5433/stock%20data?sslmode=require",
            )
            settings = PipelineSettings.from_env()
            self.assertEqual(settings.postgres_host, "db.internal")
            self.assertEqual(settings.postgres_port, 5433)
            self.assertNotIn("p@ss word", repr(settings))

    def test_postgres_schema_is_configurable_and_validated(self) -> None:
        with patch.dict(
            os.environ, {"INVESTING_POSTGRES_SCHEMA": "investing_landing"}, clear=True
        ):
            self.assertEqual(get_postgres_schema(), "investing_landing")
        with patch.dict(
            os.environ, {"INVESTING_POSTGRES_SCHEMA": "unsafe-name"}, clear=True
        ):
            with self.assertRaises(ValueError):
                get_postgres_schema()

    def test_database_url_override_takes_precedence(self) -> None:
        environment = {
            "INVESTING_DATABASE_URL": "postgresql://override/db",
        }
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(get_database_url(), "postgresql://override/db")


if __name__ == "__main__":
    unittest.main()
