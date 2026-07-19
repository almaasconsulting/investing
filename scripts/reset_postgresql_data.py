from __future__ import annotations

import os

import psycopg
from psycopg import sql

from investing.db.store import get_database_url, get_postgres_schema


PROTECTED_SCHEMAS = {"public", "information_schema", "pg_catalog"}


def main() -> None:
    landing_schema = get_postgres_schema()
    schemas = list(dict.fromkeys([landing_schema, "bronze", "silver", "gold"]))
    protected = PROTECTED_SCHEMAS.intersection(schema.lower() for schema in schemas)
    if protected:
        raise RuntimeError(
            "Refusing to reset protected PostgreSQL schema(s): " + ", ".join(sorted(protected))
        )

    database = os.getenv("INVESTING_POSTGRES_DATABASE", "investing")
    with psycopg.connect(get_database_url(), autocommit=True) as connection:
        with connection.cursor() as cursor:
            for schema in schemas:
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(schema)
                    )
                )
                print(f"Dropped application schema if present: {schema}")
    print(f"PostgreSQL application data reset completed for database: {database}")


if __name__ == "__main__":
    main()
