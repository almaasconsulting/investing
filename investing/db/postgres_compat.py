from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Iterable

import pandas as pd


def _postgres_sql(sql: str) -> str:
    translated = re.sub(r"\bDOUBLE\b(?!\s+PRECISION)", "DOUBLE PRECISION", sql)
    return translated.replace("?", "%s")


def _python_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if hasattr(value, "item"):
        return value.item()
    return value


_ALLOWED_POSTGRES_TYPES = {
    "BOOLEAN",
    "BIGINT",
    "INTEGER",
    "DOUBLE PRECISION",
    "TIMESTAMP",
    "DATE",
    "TEXT",
}


def _postgres_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series.dtype):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(series.dtype):
        return "BIGINT"
    if pd.api.types.is_float_dtype(series.dtype):
        return "DOUBLE PRECISION"
    if pd.api.types.is_datetime64_any_dtype(series.dtype):
        return "TIMESTAMP"
    sample = next((value for value in series if value is not None), None)
    if isinstance(sample, bool):
        return "BOOLEAN"
    if isinstance(sample, int):
        return "BIGINT"
    if isinstance(sample, float):
        return "DOUBLE PRECISION"
    if isinstance(sample, datetime):
        return "TIMESTAMP"
    if isinstance(sample, date):
        return "DATE"
    return "TEXT"


class PostgresResult:
    def __init__(self, cursor: Any):
        self.cursor = cursor

    def fetchone(self) -> Any:
        return self.cursor.fetchone()

    def fetchall(self) -> list[Any]:
        return self.cursor.fetchall()

    def df(self) -> pd.DataFrame:
        columns = [column.name for column in self.cursor.description or []]
        return pd.DataFrame(self.cursor.fetchall(), columns=columns)


class PostgresConnection:
    """Small connection facade used by the PostgreSQL storage service."""

    def __init__(self, database_url: str, *, schema: str = "main"):
        try:
            import psycopg
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "PostgreSQL support requires psycopg. Run: "
                "python -m pip install -r requirements.txt"
            ) from exc
        self._connection = psycopg.connect(database_url, autocommit=True)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
            self._connection.close()
            raise ValueError("PostgreSQL schema must be a simple SQL identifier.")
        cursor = self._connection.cursor()
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        cursor.execute(f'SET search_path TO "{schema}", public')

    def execute(
        self, sql: str, params: Iterable[Any] | None = None
    ) -> PostgresResult:
        statements = [part.strip() for part in sql.split(";") if part.strip()]
        if len(statements) > 1 and params:
            raise ValueError("Parameters cannot be used with multiple SQL statements.")
        cursor = None
        for statement in statements or [sql]:
            cursor = self._connection.cursor()
            cursor.execute(
                _postgres_sql(statement),
                tuple(_python_value(value) for value in (params or ())),
            )
        assert cursor is not None
        return PostgresResult(cursor)

    def register(
        self,
        name: str,
        frame: pd.DataFrame,
        *,
        column_types: dict[str, str] | None = None,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"Unsafe temporary table name: {name}")
        column_types = {
            column: sql_type.upper()
            for column, sql_type in (column_types or {}).items()
        }
        invalid_types = set(column_types.values()) - _ALLOWED_POSTGRES_TYPES
        if invalid_types:
            raise ValueError(
                "Unsupported PostgreSQL temporary-column type(s): "
                + ", ".join(sorted(invalid_types))
            )
        self.execute(f'DROP TABLE IF EXISTS "{name}"')
        columns = [
            f'"{column}" {column_types.get(column, _postgres_type(frame[column]))}'
            for column in frame.columns
        ]
        self.execute(
            f'CREATE TEMP TABLE "{name}" ({", ".join(columns)}) '
            "ON COMMIT PRESERVE ROWS"
        )
        if frame.empty:
            return
        placeholders = ", ".join(["%s"] * len(frame.columns))
        quoted_columns = ", ".join(f'"{column}"' for column in frame.columns)
        rows = [
            tuple(_python_value(value) for value in row)
            for row in frame.itertuples(index=False, name=None)
        ]
        cursor = self._connection.cursor()
        cursor.executemany(
            f'INSERT INTO "{name}" ({quoted_columns}) VALUES ({placeholders})', rows
        )

    def unregister(self, name: str) -> None:
        self.execute(f'DROP TABLE IF EXISTS "{name}"')

    def transaction(self):
        """Return psycopg's transaction context for multi-statement writes."""
        return self._connection.transaction()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "PostgresConnection":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
