from __future__ import annotations

import json
import os
import hashlib
import math
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import pandas as pd

STOCK_UNIVERSE_COLUMNS = [
    "symbol",
    "yahoo_symbol",
    "name",
    "full_name",
    "country",
    "market",
    "exchange",
    "exchange_mic",
    "isin",
    "currency",
    "source",
    "source_url",
    "is_active",
    "refreshed_at",
]

_INITIALIZED_DB_PATHS: set[str] = set()
_INIT_LOCK = threading.Lock()

_FUNDAMENTAL_DOUBLE_COLUMNS = [
    "market_cap", "pe_ratio", "eps", "beta", "shares_outstanding", "revenue",
    "prev_close", "revenue_growth", "earnings_growth", "return_on_equity",
    "profit_margins", "debt_to_equity", "current_ratio", "free_cashflow",
    "altman_z_score", "return_on_assets", "operating_margins", "gross_margins",
    "free_cashflow_yield", "price_to_book", "enterprise_to_ebitda", "peg_ratio",
    "payout_ratio", "funds_from_operations", "funds_from_operations_yield",
    "dividend_cagr_5y",
]
_FUNDAMENTAL_INTEGER_COLUMNS = [
    "dividend_years_paid", "consecutive_dividend_years", "latest_dividend_year",
]
_FUNDAMENTAL_COLUMN_TYPES = {
    **{column: "DOUBLE PRECISION" for column in _FUNDAMENTAL_DOUBLE_COLUMNS},
    **{column: "INTEGER" for column in _FUNDAMENTAL_INTEGER_COLUMNS},
    "snapshot_date": "DATE",
    "ingested_at": "TIMESTAMP",
}

_ANALYSIS_COLUMN_TYPES = {
    "run_timestamp": "TIMESTAMP",
    "days": "INTEGER",
    "min_score": "DOUBLE PRECISION",
    "max_volatility": "DOUBLE PRECISION",
}
_STOCK_UNIVERSE_COLUMN_TYPES = {
    "is_active": "BOOLEAN",
    "refreshed_at": "TIMESTAMP",
}
_NEWS_COLUMN_TYPES = {
    "published_at": "TIMESTAMP",
    "fetched_at": "TIMESTAMP",
}
_FINANCIAL_STATEMENT_COLUMN_TYPES = {
    "fiscal_period_end": "DATE",
    "value": "DOUBLE PRECISION",
    "reported_at": "TIMESTAMP",
    "fetched_at": "TIMESTAMP",
}


def get_database_url() -> str:
    url = os.getenv("INVESTING_DATABASE_URL", "").strip()
    if url:
        return url
    host = os.getenv("INVESTING_POSTGRES_HOST", "localhost").strip()
    port = int(os.getenv("INVESTING_POSTGRES_PORT", "5432"))
    database = os.getenv("INVESTING_POSTGRES_DATABASE", "investing").strip()
    user = os.getenv("INVESTING_POSTGRES_USER", "investing").strip()
    password = os.getenv("INVESTING_POSTGRES_PASSWORD", "")
    sslmode = os.getenv("INVESTING_POSTGRES_SSLMODE", "prefer").strip()
    if not host or not database or not user:
        raise ValueError("PostgreSQL host, database, and user must not be empty.")
    credentials = quote(user, safe="")
    if password:
        credentials += f":{quote(password, safe='')}"
    url = (
        f"postgresql://{credentials}@{host}:{port}/{quote(database, safe='')}"
        f"?sslmode={quote(sslmode, safe='')}"
    )
    return url


def get_postgres_schema() -> str:
    schema = os.getenv("INVESTING_POSTGRES_SCHEMA", "main").strip()
    if not schema or not schema.replace("_", "a").isalnum() or schema[0].isdigit():
        raise ValueError("INVESTING_POSTGRES_SCHEMA must be a simple SQL identifier.")
    return schema


def init_db(db_path: Path | str | None = None) -> Any:
    from investing.db.postgres_compat import PostgresConnection

    path_key = "postgresql:" + hashlib.sha256(
        get_database_url().encode("utf-8")
    ).hexdigest()
    con = PostgresConnection(get_database_url(), schema=get_postgres_schema())

    # Schema creation/migration only needs to run once per Python process.
    with _INIT_LOCK:
        if path_key in _INITIALIZED_DB_PATHS:
            return con
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_history (
            date DATE,
            ticker VARCHAR,
            name VARCHAR,
            country VARCHAR,
            exchange VARCHAR,
            data_source VARCHAR,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume BIGINT,
            ma20 DOUBLE,
            ma50 DOUBLE,
            ma200 DOUBLE,
            rsi14 DOUBLE,
            direction VARCHAR,
            signal_summary VARCHAR,
            price_source VARCHAR,
            yahoo_open DOUBLE,
            yahoo_high DOUBLE,
            yahoo_low DOUBLE,
            yahoo_close DOUBLE,
            yahoo_volume DOUBLE,
            investing_open DOUBLE,
            investing_high DOUBLE,
            investing_low DOUBLE,
            investing_close DOUBLE,
            investing_volume DOUBLE,
            ingested_at TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS fundamental_snapshot (
            snapshot_date DATE,
            ticker VARCHAR,
            name VARCHAR,
            country VARCHAR,
            exchange VARCHAR,
            data_source VARCHAR,
            market_cap DOUBLE,
            pe_ratio DOUBLE,
            eps DOUBLE,
            dividend_yield VARCHAR,
            beta DOUBLE,
            one_year_change VARCHAR,
            shares_outstanding DOUBLE,
            revenue DOUBLE,
            prev_close DOUBLE,
            sector VARCHAR,
            industry VARCHAR,
            revenue_growth DOUBLE,
            earnings_growth DOUBLE,
            return_on_equity DOUBLE,
            profit_margins DOUBLE,
            debt_to_equity DOUBLE,
            current_ratio DOUBLE,
            free_cashflow DOUBLE,
            altman_z_score DOUBLE,
            altman_z_zone VARCHAR,
            return_on_assets DOUBLE,
            operating_margins DOUBLE,
            gross_margins DOUBLE,
            free_cashflow_yield DOUBLE,
            price_to_book DOUBLE,
            enterprise_to_ebitda DOUBLE,
            peg_ratio DOUBLE,
            payout_ratio DOUBLE,
            funds_from_operations DOUBLE,
            funds_from_operations_yield DOUBLE,
            dividend_years_paid INTEGER,
            consecutive_dividend_years INTEGER,
            dividend_cagr_5y DOUBLE,
            latest_dividend_year INTEGER,
            field_sources_json VARCHAR,
            provider_payloads_json VARCHAR,
            record_hash VARCHAR,
            ingested_at TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS stock_universe (
            symbol VARCHAR,
            yahoo_symbol VARCHAR,
            name VARCHAR,
            full_name VARCHAR,
            country VARCHAR,
            market VARCHAR,
            exchange VARCHAR,
            exchange_mic VARCHAR,
            isin VARCHAR,
            currency VARCHAR,
            source VARCHAR,
            source_url VARCHAR,
            is_active BOOLEAN,
            refreshed_at TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS analysis_snapshot (
            run_timestamp TIMESTAMP,
            symbol VARCHAR,
            country VARCHAR,
            name VARCHAR,
            exchange VARCHAR,
            yahoo_symbol VARCHAR,
            universe_market VARCHAR,
            universe_isin VARCHAR,
            data_source VARCHAR,
            days INTEGER,
            min_score DOUBLE,
            max_volatility DOUBLE,
            notes VARCHAR,
            scorecard_json VARCHAR,
            technical_json VARCHAR,
            fundamentals_json VARCHAR,
            metrics_json VARCHAR,
            error VARCHAR
        );
        CREATE TABLE IF NOT EXISTS news_article_landing (
            article_id VARCHAR,
            provider_article_id VARCHAR,
            ticker VARCHAR,
            yahoo_symbol VARCHAR,
            country VARCHAR,
            provider VARCHAR,
            published_at TIMESTAMP,
            title VARCHAR,
            publisher VARCHAR,
            summary VARCHAR,
            url VARCHAR,
            content_type VARCHAR,
            raw_payload_json VARCHAR,
            fetched_at TIMESTAMP,
            record_hash VARCHAR
        );
        CREATE TABLE IF NOT EXISTS financial_statement_landing (
            ticker VARCHAR,
            yahoo_symbol VARCHAR,
            country VARCHAR,
            provider VARCHAR,
            statement_type VARCHAR,
            period_type VARCHAR,
            fiscal_period_end DATE,
            line_item VARCHAR,
            line_item_label VARCHAR,
            value DOUBLE,
            currency VARCHAR,
            reported_at TIMESTAMP,
            fetched_at TIMESTAMP,
            record_hash VARCHAR,
            raw_payload_json VARCHAR
        );
        CREATE TABLE IF NOT EXISTS stock_update_status (
            update_type VARCHAR,
            ticker VARCHAR,
            country VARCHAR,
            last_attempted_at TIMESTAMP,
            last_succeeded_at TIMESTAMP,
            last_error VARCHAR
        );
        """
    )
    con.execute("ALTER TABLE stock_history ADD COLUMN IF NOT EXISTS data_source VARCHAR;")
    con.execute("ALTER TABLE stock_history ADD COLUMN IF NOT EXISTS price_source VARCHAR;")
    for provider in ("yahoo", "investing"):
        for field in ("open", "high", "low", "close", "volume"):
            con.execute(
                f"ALTER TABLE stock_history ADD COLUMN IF NOT EXISTS {provider}_{field} DOUBLE;"
            )
    con.execute("ALTER TABLE stock_history ADD COLUMN IF NOT EXISTS ingested_at TIMESTAMP;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS data_source VARCHAR;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS sector VARCHAR;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS industry VARCHAR;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS revenue_growth DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS earnings_growth DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS return_on_equity DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS profit_margins DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS debt_to_equity DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS current_ratio DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS free_cashflow DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS altman_z_score DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS altman_z_zone VARCHAR;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS return_on_assets DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS operating_margins DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS gross_margins DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS free_cashflow_yield DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS price_to_book DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS enterprise_to_ebitda DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS peg_ratio DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS payout_ratio DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS funds_from_operations DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS funds_from_operations_yield DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS dividend_years_paid INTEGER;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS consecutive_dividend_years INTEGER;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS dividend_cagr_5y DOUBLE;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS latest_dividend_year INTEGER;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS field_sources_json VARCHAR;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS provider_payloads_json VARCHAR;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS record_hash VARCHAR;")
    con.execute("ALTER TABLE fundamental_snapshot ADD COLUMN IF NOT EXISTS ingested_at TIMESTAMP;")
    con.execute("ALTER TABLE stock_universe ADD COLUMN IF NOT EXISTS yahoo_symbol VARCHAR;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS run_timestamp TIMESTAMP;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS yahoo_symbol VARCHAR;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS universe_market VARCHAR;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS universe_isin VARCHAR;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS days INTEGER;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS min_score DOUBLE;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS max_volatility DOUBLE;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS notes VARCHAR;")
    for index_sql in (
            "CREATE INDEX IF NOT EXISTS idx_stock_history_lookup "
            "ON stock_history (country, ticker, date)",
            "CREATE INDEX IF NOT EXISTS idx_fundamental_lookup "
            "ON fundamental_snapshot (country, ticker, snapshot_date)",
            "CREATE INDEX IF NOT EXISTS idx_analysis_lookup "
            "ON analysis_snapshot (country, symbol, run_timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_universe_lookup "
            "ON stock_universe (country, symbol)",
            "CREATE INDEX IF NOT EXISTS idx_update_queue "
            "ON stock_update_status (update_type, last_attempted_at)",
            "CREATE INDEX IF NOT EXISTS idx_news_lookup "
            "ON news_article_landing (country, ticker, published_at)",
            "CREATE INDEX IF NOT EXISTS idx_statement_lookup "
            "ON financial_statement_landing "
            "(country, ticker, period_type, fiscal_period_end)",
    ):
        con.execute(index_sql)
    _INITIALIZED_DB_PATHS.add(path_key)
    return con


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (date, datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        return _json_safe(value.item())
    return value


def _to_json(value: Any) -> str:
    return json.dumps(
        _json_safe(value or {}),
        default=_json_default,
        sort_keys=True,
        allow_nan=False,
    )


def _from_json(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _fetch_frame(
    query: str,
    params: Iterable[Any] | None = None,
    db_path: Path | None = None,
) -> pd.DataFrame:
    """Execute a query using a short-lived PostgreSQL connection."""
    con = init_db(db_path)
    try:
        return con.execute(query, list(params or [])).df()
    finally:
        con.close()


def save_stock_history(
    df: pd.DataFrame,
    ticker: str,
    name: str,
    country: str,
    exchange: str = "",
    data_source: str = "",
    db_path: Path | None = None,
) -> None:
    con = init_db(db_path)
    df = df.copy()
    df["ticker"] = ticker
    df["name"] = name
    df["country"] = country
    df["exchange"] = exchange
    df["data_source"] = data_source
    df["ingested_at"] = _utc_now()

    optional_columns = [
        "ma20", "ma50", "ma200", "rsi14", "direction", "signal_summary", "price_source",
        *[
            f"{provider}_{field}"
            for provider in ("yahoo", "investing")
            for field in ("open", "high", "low", "close", "volume")
        ],
    ]
    for column in optional_columns:
        if column not in df.columns:
            df[column] = None

    numeric_columns = [
        "open", "high", "low", "close", "volume",
        "ma20", "ma50", "ma200", "rsi14",
        *[
            f"{provider}_{field}"
            for provider in ("yahoo", "investing")
            for field in ("open", "high", "low", "close", "volume")
        ],
    ]
    for column in numeric_columns:
        if column not in df.columns:
            df[column] = float("nan")
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    con.register("new_data", df)
    try:
        con.execute(
            """
            INSERT INTO stock_history (
                date, ticker, name, country, exchange, data_source, open, high, low, close, volume,
                ma20, ma50, ma200, rsi14, direction, signal_summary, price_source,
                yahoo_open, yahoo_high, yahoo_low, yahoo_close, yahoo_volume,
                investing_open, investing_high, investing_low, investing_close, investing_volume,
                ingested_at
            )
            SELECT
                date, ticker, name, country, exchange, data_source,
                CAST(open AS DOUBLE PRECISION), CAST(high AS DOUBLE PRECISION),
                CAST(low AS DOUBLE PRECISION), CAST(close AS DOUBLE PRECISION),
                CAST(volume AS BIGINT),
                CAST(ma20 AS DOUBLE PRECISION), CAST(ma50 AS DOUBLE PRECISION),
                CAST(ma200 AS DOUBLE PRECISION), CAST(rsi14 AS DOUBLE PRECISION),
                direction, signal_summary, price_source,
                CAST(yahoo_open AS DOUBLE PRECISION), CAST(yahoo_high AS DOUBLE PRECISION),
                CAST(yahoo_low AS DOUBLE PRECISION), CAST(yahoo_close AS DOUBLE PRECISION),
                CAST(yahoo_volume AS DOUBLE PRECISION),
                CAST(investing_open AS DOUBLE PRECISION), CAST(investing_high AS DOUBLE PRECISION),
                CAST(investing_low AS DOUBLE PRECISION), CAST(investing_close AS DOUBLE PRECISION),
                CAST(investing_volume AS DOUBLE PRECISION), ingested_at
            FROM new_data
            """
        )
    finally:
        con.unregister("new_data")
        con.close()


def save_fundamental_snapshot(
    fundamentals: dict[str, Any],
    ticker: str,
    name: str,
    country: str,
    exchange: str = "",
    data_source: str = "",
    snapshot_date: date | None = None,
    db_path: Path | None = None,
) -> bool:
    con = init_db(db_path)
    snapshot_date = snapshot_date or date.today()
    record_hash = hashlib.sha256(_to_json(fundamentals).encode("utf-8")).hexdigest()
    existing = con.execute(
        """
        SELECT record_hash
        FROM fundamental_snapshot
        WHERE snapshot_date = ? AND LOWER(ticker) = ? AND LOWER(country) = ?
        ORDER BY ingested_at DESC NULLS LAST
        LIMIT 1
        """,
        [snapshot_date, ticker.lower(), country.lower()],
    ).fetchone()
    if existing and existing[0] == record_hash:
        con.close()
        return False
    row = {
        "snapshot_date": snapshot_date,
        "ticker": ticker,
        "name": name,
        "country": country,
        "exchange": exchange,
        "data_source": data_source,
        "market_cap": fundamentals.get("market_cap"),
        "pe_ratio": fundamentals.get("pe_ratio"),
        "eps": fundamentals.get("eps"),
        "dividend_yield": fundamentals.get("dividend_yield"),
        "beta": fundamentals.get("beta"),
        "one_year_change": fundamentals.get("one_year_change"),
        "shares_outstanding": fundamentals.get("shares_outstanding"),
        "revenue": fundamentals.get("revenue"),
        "prev_close": fundamentals.get("prev_close"),
        "sector": fundamentals.get("sector"),
        "industry": fundamentals.get("industry"),
        "revenue_growth": fundamentals.get("revenue_growth"),
        "earnings_growth": fundamentals.get("earnings_growth"),
        "return_on_equity": fundamentals.get("return_on_equity"),
        "profit_margins": fundamentals.get("profit_margins"),
        "debt_to_equity": fundamentals.get("debt_to_equity"),
        "current_ratio": fundamentals.get("current_ratio"),
        "free_cashflow": fundamentals.get("free_cashflow"),
        "altman_z_score": fundamentals.get("altman_z_score"),
        "altman_z_zone": fundamentals.get("altman_z_zone"),
        "return_on_assets": fundamentals.get("return_on_assets"),
        "operating_margins": fundamentals.get("operating_margins"),
        "gross_margins": fundamentals.get("gross_margins"),
        "free_cashflow_yield": fundamentals.get("free_cashflow_yield"),
        "price_to_book": fundamentals.get("price_to_book"),
        "enterprise_to_ebitda": fundamentals.get("enterprise_to_ebitda"),
        "peg_ratio": fundamentals.get("peg_ratio"),
        "payout_ratio": fundamentals.get("payout_ratio"),
        "funds_from_operations": fundamentals.get("funds_from_operations"),
        "funds_from_operations_yield": fundamentals.get("funds_from_operations_yield"),
        "dividend_years_paid": fundamentals.get("dividend_years_paid"),
        "consecutive_dividend_years": fundamentals.get("consecutive_dividend_years"),
        "dividend_cagr_5y": fundamentals.get("dividend_cagr_5y"),
        "latest_dividend_year": fundamentals.get("latest_dividend_year"),
        "field_sources_json": _to_json(fundamentals.get("field_sources", {})),
        "provider_payloads_json": _to_json(fundamentals.get("provider_payloads", {})),
        "record_hash": record_hash,
        "ingested_at": _utc_now(),
    }
    df = pd.DataFrame([row])
    for column in _FUNDAMENTAL_DOUBLE_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    for column in _FUNDAMENTAL_INTEGER_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce").astype("Int64")
    con.register("new_data", df, column_types=_FUNDAMENTAL_COLUMN_TYPES)
    try:
        con.execute(
            """
        INSERT INTO fundamental_snapshot (
            snapshot_date, ticker, name, country, exchange, data_source, market_cap,
            pe_ratio, eps, dividend_yield, beta, one_year_change, shares_outstanding,
            revenue, prev_close, sector, industry, revenue_growth, earnings_growth,
            return_on_equity, profit_margins, debt_to_equity, current_ratio, free_cashflow,
            altman_z_score, altman_z_zone, return_on_assets, operating_margins,
            gross_margins, free_cashflow_yield, price_to_book, enterprise_to_ebitda,
            peg_ratio, payout_ratio, funds_from_operations, funds_from_operations_yield,
            dividend_years_paid, consecutive_dividend_years, dividend_cagr_5y,
            latest_dividend_year, field_sources_json, provider_payloads_json, record_hash, ingested_at
        )
        SELECT
            snapshot_date, ticker, name, country, exchange, data_source,
            CAST(market_cap AS DOUBLE PRECISION), CAST(pe_ratio AS DOUBLE PRECISION),
            CAST(eps AS DOUBLE PRECISION), dividend_yield, CAST(beta AS DOUBLE PRECISION),
            one_year_change, CAST(shares_outstanding AS DOUBLE PRECISION),
            CAST(revenue AS DOUBLE PRECISION), CAST(prev_close AS DOUBLE PRECISION),
            sector, industry, CAST(revenue_growth AS DOUBLE PRECISION),
            CAST(earnings_growth AS DOUBLE PRECISION),
            CAST(return_on_equity AS DOUBLE PRECISION),
            CAST(profit_margins AS DOUBLE PRECISION),
            CAST(debt_to_equity AS DOUBLE PRECISION),
            CAST(current_ratio AS DOUBLE PRECISION),
            CAST(free_cashflow AS DOUBLE PRECISION),
            CAST(altman_z_score AS DOUBLE PRECISION), altman_z_zone,
            CAST(return_on_assets AS DOUBLE PRECISION),
            CAST(operating_margins AS DOUBLE PRECISION),
            CAST(gross_margins AS DOUBLE PRECISION),
            CAST(free_cashflow_yield AS DOUBLE PRECISION),
            CAST(price_to_book AS DOUBLE PRECISION),
            CAST(enterprise_to_ebitda AS DOUBLE PRECISION),
            CAST(peg_ratio AS DOUBLE PRECISION), CAST(payout_ratio AS DOUBLE PRECISION),
            CAST(funds_from_operations AS DOUBLE PRECISION),
            CAST(funds_from_operations_yield AS DOUBLE PRECISION),
            CAST(dividend_years_paid AS INTEGER),
            CAST(consecutive_dividend_years AS INTEGER),
            CAST(dividend_cagr_5y AS DOUBLE PRECISION),
            CAST(latest_dividend_year AS INTEGER), field_sources_json,
            provider_payloads_json, record_hash, ingested_at
        FROM new_data
        """
        )
    finally:
        con.unregister("new_data")
        con.close()
    return True


def query_stock_history(ticker: str, country: str = "norway", db_path: Path | None = None) -> pd.DataFrame:
    con = init_db(db_path)
    try:
        query = """
            SELECT *
            FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY LOWER(ticker), LOWER(country), date
                    ORDER BY ingested_at DESC NULLS LAST
                ) AS row_rank
                FROM stock_history
                WHERE (LOWER(ticker) = ? OR LOWER(name) = ?)
                  AND LOWER(country) = ?
            )
            WHERE row_rank = 1
            ORDER BY date
        """
        frame = con.execute(
            query, [ticker.lower(), ticker.lower(), country.lower()]
        ).df()
        return frame.drop(columns=["row_rank"], errors="ignore")
    finally:
        con.close()


def query_stock_histories(
    stocks: Iterable[tuple[str, str]],
    days: int = 365,
    db_path: Path | None = None,
) -> pd.DataFrame:
    """Return the latest stored close for many stocks in one database query."""
    requested_rows = []
    seen: set[tuple[str, str]] = set()
    for symbol, country in stocks:
        symbol = str(symbol or "").strip()
        country = str(country or "norway").strip().lower()
        identity = (symbol.lower(), country)
        if not symbol or identity in seen:
            continue
        seen.add(identity)
        requested_rows.append(
            {
                "symbol": symbol,
                "lookup_symbol": symbol.lower(),
                "country": country,
            }
        )

    if not requested_rows:
        return pd.DataFrame(columns=["date", "symbol", "country", "close"])
    if days < 1:
        raise ValueError("days must be at least 1")

    con = init_db(db_path)
    try:
        con.register(
            "requested_stock_histories",
            pd.DataFrame(requested_rows),
            column_types={
                "symbol": "TEXT",
                "lookup_symbol": "TEXT",
                "country": "TEXT",
            },
        )
        query = """
            SELECT date, symbol, country, close
            FROM (
                SELECT
                    h.date,
                    r.symbol,
                    r.country,
                    h.close,
                    ROW_NUMBER() OVER (
                        PARTITION BY r.lookup_symbol, r.country, h.date
                        ORDER BY h.ingested_at DESC NULLS LAST
                    ) AS row_rank
                FROM stock_history h
                JOIN requested_stock_histories r
                  ON LOWER(h.ticker) = r.lookup_symbol
                 AND LOWER(h.country) = r.country
                WHERE h.date >= CURRENT_DATE - CAST(? AS INTEGER)
                  AND h.close IS NOT NULL
            ) ranked
            WHERE row_rank = 1
            ORDER BY date, symbol
        """
        return con.execute(query, [int(days)]).df()
    finally:
        con.unregister("requested_stock_histories")
        con.close()


def query_fundamental_snapshots(ticker: str, country: str = "norway", db_path: Path | None = None) -> pd.DataFrame:
    con = init_db(db_path)
    try:
        query = """
            SELECT *
            FROM fundamental_snapshot
            WHERE (LOWER(ticker) = ? OR LOWER(name) = ?)
              AND LOWER(country) = ?
            ORDER BY snapshot_date
        """
        return con.execute(
            query, [ticker.lower(), ticker.lower(), country.lower()]
        ).df()
    finally:
        con.close()


def save_analysis_snapshots(
    results: list[dict],
    days: int | None = None,
    min_score: float | None = None,
    max_volatility: float | None = None,
    run_timestamp: datetime | None = None,
    db_path: Path | None = None,
) -> int:
    rows = []
    run_timestamp = run_timestamp or _utc_now()
    for result in results:
        symbol = str(result.get("symbol", "") or "").strip()
        country = str(result.get("country", "") or "").strip().lower()
        if not symbol or not country:
            continue
        rows.append(
            {
                "run_timestamp": run_timestamp,
                "symbol": symbol.upper(),
                "country": country,
                "name": result.get("name", symbol),
                "exchange": result.get("exchange", ""),
                "yahoo_symbol": result.get("yahoo_symbol", ""),
                "universe_market": result.get("universe_market", ""),
                "universe_isin": result.get("universe_isin", ""),
                "data_source": result.get("data_source", ""),
                "days": days,
                "min_score": min_score,
                "max_volatility": max_volatility,
                "notes": result.get("notes", ""),
                "scorecard_json": _to_json(result.get("scorecard", {})),
                "technical_json": _to_json(result.get("technical", {})),
                "fundamentals_json": _to_json(result.get("fundamentals", {})),
                "metrics_json": _to_json(result.get("metrics", {})),
                "error": result.get("error", ""),
            }
        )

    if not rows:
        return 0

    con = init_db(db_path)
    df = pd.DataFrame(rows)
    con.register(
        "new_analysis_snapshot", df, column_types=_ANALYSIS_COLUMN_TYPES
    )
    con.execute(
        """
        INSERT INTO analysis_snapshot (
            run_timestamp, symbol, country, name, exchange, yahoo_symbol,
            universe_market, universe_isin, data_source, days, min_score,
            max_volatility, notes, scorecard_json, technical_json,
            fundamentals_json, metrics_json, error
        )
        SELECT
            run_timestamp, symbol, country, name, exchange, yahoo_symbol,
            universe_market, universe_isin, data_source, days, min_score,
            max_volatility, notes, scorecard_json, technical_json,
            fundamentals_json, metrics_json, error
        FROM new_analysis_snapshot
        """
    )
    con.unregister("new_analysis_snapshot")
    con.close()
    return len(rows)


def _history_for_result(symbol: str, country: str, db_path: Path | None = None) -> pd.DataFrame:
    history = query_stock_history(symbol, country=country, db_path=db_path)
    if history.empty:
        return pd.DataFrame()

    columns = [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "ma20",
        "ma50",
        "ma200",
        "rsi14",
        "direction",
        "signal_summary",
    ]
    return history[[column for column in columns if column in history.columns]].drop_duplicates("date")


def query_latest_analysis_snapshots(
    countries: Iterable[str] | str | None = None,
    symbols: Iterable[str] | str | None = None,
    include_history: bool = True,
    db_path: Path | None = None,
) -> list[dict]:
    conditions: list[str] = []
    params: list[str] = []

    country_values = _coerce_filter_values(countries)
    if country_values:
        placeholders = ",".join("?" for _ in country_values)
        conditions.append(f"LOWER(country) IN ({placeholders})")
        params.extend(country.lower() for country in country_values)

    symbol_values = _coerce_filter_values(symbols)
    if symbol_values:
        placeholders = ",".join("?" for _ in symbol_values)
        conditions.append(f"UPPER(symbol) IN ({placeholders})")
        params.extend(symbol.upper() for symbol in symbol_values)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    df = _fetch_frame(
        f"""
        SELECT *
        FROM (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY LOWER(symbol), LOWER(country)
                    ORDER BY run_timestamp DESC
                ) AS snapshot_rank
            FROM analysis_snapshot
            {where_clause}
        )
        WHERE snapshot_rank = 1
        ORDER BY country, symbol
        """,
        params,
        db_path,
    )

    results: list[dict] = []
    for row in df.to_dict("records"):
        result = {
            "symbol": row.get("symbol"),
            "name": row.get("name"),
            "country": row.get("country"),
            "exchange": row.get("exchange"),
            "yahoo_symbol": row.get("yahoo_symbol"),
            "universe_market": row.get("universe_market"),
            "universe_isin": row.get("universe_isin"),
            "data_source": row.get("data_source"),
            "notes": row.get("notes"),
            "scorecard": _from_json(row.get("scorecard_json")),
            "technical": _from_json(row.get("technical_json")),
            "fundamentals": _from_json(row.get("fundamentals_json")),
            "metrics": _from_json(row.get("metrics_json")),
            "error": row.get("error") or "",
            "last_run_at": row.get("run_timestamp"),
            "days": row.get("days"),
            "min_score": row.get("min_score"),
            "max_volatility": row.get("max_volatility"),
            "cached": True,
        }
        if include_history and not result["error"]:
            result["data"] = _history_for_result(
                str(result["symbol"]),
                country=str(result["country"]),
                db_path=db_path,
            )
        results.append(result)
    return results


def _coerce_filter_values(values: Iterable[str] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    return [value.strip() for value in values if value and value.strip()]


def save_stock_universe(
    universe_df: pd.DataFrame,
    replace_countries: Iterable[str] | str | None = None,
    db_path: Path | None = None,
) -> int:
    """Replace stock universe rows for the supplied countries and return inserted rows."""
    if universe_df.empty:
        return 0

    con = init_db(db_path)
    df = universe_df.copy()
    for column in STOCK_UNIVERSE_COLUMNS:
        if column not in df.columns:
            df[column] = None

    df = df[STOCK_UNIVERSE_COLUMNS]
    string_columns = [column for column in STOCK_UNIVERSE_COLUMNS if column not in {"is_active", "refreshed_at"}]
    for column in string_columns:
        df[column] = df[column].fillna("").astype(str).str.strip()

    df = df[(df["symbol"] != "") & (df["country"] != "")]
    if df.empty:
        con.close()
        return 0

    df["is_active"] = df["is_active"].fillna(True).astype(bool)

    countries = _coerce_filter_values(replace_countries) or sorted(df["country"].str.lower().unique().tolist())
    transaction = con.transaction() if hasattr(con, "transaction") else nullcontext()
    with transaction:
        if countries:
            placeholders = ",".join("?" for _ in countries)
            con.execute(
                f"DELETE FROM stock_universe WHERE LOWER(country) IN ({placeholders})",
                [country.lower() for country in countries],
            )

        con.register(
            "new_stock_universe", df, column_types=_STOCK_UNIVERSE_COLUMN_TYPES
        )
        con.execute(
            """
            INSERT INTO stock_universe (
                symbol, yahoo_symbol, name, full_name, country, market, exchange, exchange_mic,
                isin, currency, source, source_url, is_active, refreshed_at
            )
            SELECT
                symbol, yahoo_symbol, name, full_name, country, market, exchange, exchange_mic,
                isin, currency, source, source_url, is_active, refreshed_at
            FROM new_stock_universe
            """
        )
        con.unregister("new_stock_universe")
    con.close()
    return len(df)


def query_stock_universe(
    countries: Iterable[str] | str | None = None,
    symbols: Iterable[str] | str | None = None,
    markets: Iterable[str] | str | None = None,
    active_only: bool = True,
    db_path: Path | None = None,
) -> pd.DataFrame:
    conditions: list[str] = []
    params: list[str] = []

    if active_only:
        conditions.append("u.is_active")

    country_values = _coerce_filter_values(countries)
    if country_values:
        placeholders = ",".join("?" for _ in country_values)
        conditions.append(f"LOWER(u.country) IN ({placeholders})")
        params.extend(country.lower() for country in country_values)

    symbol_values = _coerce_filter_values(symbols)
    if symbol_values:
        placeholders = ",".join("?" for _ in symbol_values)
        conditions.append(f"UPPER(u.symbol) IN ({placeholders})")
        params.extend(symbol.upper() for symbol in symbol_values)

    market_values = _coerce_filter_values(markets)
    if market_values:
        lower_placeholders = ",".join("?" for _ in market_values)
        upper_placeholders = ",".join("?" for _ in market_values)
        conditions.append(
            f"""(
                LOWER(u.market) IN ({lower_placeholders})
                OR LOWER(u.exchange) IN ({lower_placeholders})
                OR UPPER(u.exchange_mic) IN ({upper_placeholders})
            )"""
        )
        params.extend(market.lower() for market in market_values)
        params.extend(market.lower() for market in market_values)
        params.extend(market.upper() for market in market_values)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    return _fetch_frame(
        f"""
        SELECT
            u.symbol, u.yahoo_symbol, u.name, u.full_name, u.country, u.market,
            u.exchange, u.exchange_mic, u.isin, u.currency, u.source,
            u.source_url, u.is_active, u.refreshed_at
        FROM stock_universe u
        {where_clause}
        ORDER BY u.country, u.market, u.symbol
        """,
        params,
        db_path,
    )


def query_stock_universe_symbols(
    countries: Iterable[str] | str | None = None,
    symbols: Iterable[str] | str | None = None,
    markets: Iterable[str] | str | None = None,
    active_only: bool = True,
    db_path: Path | None = None,
) -> list[str]:
    df = query_stock_universe(
        countries=countries,
        symbols=symbols,
        markets=markets,
        active_only=active_only,
        db_path=db_path,
    )
    return df["symbol"].dropna().astype(str).tolist()


def save_stock_update_status(
    *,
    update_type: str,
    ticker: str,
    country: str,
    succeeded: bool,
    error: str = "",
    attempted_at: datetime | None = None,
    db_path: Path | None = None,
) -> None:
    """Upsert the latest attempt so failing stocks cannot starve the queue."""
    con = init_db(db_path)
    attempted_at = attempted_at or _utc_now()
    existing = con.execute(
        """
        SELECT last_succeeded_at FROM stock_update_status
        WHERE lower(update_type) = lower(?)
          AND upper(ticker) = upper(?)
          AND lower(country) = lower(?)
        """,
        [update_type, ticker, country],
    ).fetchone()
    last_succeeded_at = attempted_at if succeeded else (existing[0] if existing else None)
    con.execute(
        """
        DELETE FROM stock_update_status
        WHERE lower(update_type) = lower(?)
          AND upper(ticker) = upper(?)
          AND lower(country) = lower(?)
        """,
        [update_type, ticker, country],
    )
    con.execute(
        """
        INSERT INTO stock_update_status (
            update_type, ticker, country, last_attempted_at,
            last_succeeded_at, last_error
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            update_type.lower(), ticker.upper(), country.lower(), attempted_at,
            last_succeeded_at, "" if succeeded else error,
        ],
    )
    con.close()


def _query_stale_stock_queue(
    *,
    update_type: str,
    countries: Iterable[str] | str | None,
    limit: int | None,
    minimum_success_age_hours: float | None,
    db_path: Path | None,
) -> pd.DataFrame:
    country_values = _coerce_filter_values(countries)
    conditions = ["u.is_active"]
    params: list[Any] = [update_type.lower(), update_type.lower()]
    if minimum_success_age_hours is not None:
        conditions.append(
            "(s.last_succeeded_at IS NULL OR "
            "s.last_succeeded_at <= CURRENT_TIMESTAMP - (? * INTERVAL '1 hour'))"
        )
        params.append(float(minimum_success_age_hours))
    if country_values:
        placeholders = ",".join("?" for _ in country_values)
        conditions.append(f"lower(u.country) in ({placeholders})")
        params.extend(country.lower() for country in country_values)
    limit_clause = ""
    if limit is not None and limit > 0:
        limit_clause = "LIMIT ?"
        params.append(int(limit))
    return _fetch_frame(
        f"""
        WITH analysis_history AS (
            SELECT upper(symbol) AS ticker, lower(country) AS country,
                   max(run_timestamp) AS last_attempted_at
            FROM analysis_snapshot
            GROUP BY upper(symbol), lower(country)
        ),
        content_history AS (
            SELECT upper(ticker) AS ticker, lower(country) AS country,
                   max(fetched_at) AS last_attempted_at
            FROM (
                SELECT ticker, country, fetched_at FROM news_article_landing
                UNION ALL
                SELECT ticker, country, fetched_at FROM financial_statement_landing
            ) history
            GROUP BY upper(ticker), lower(country)
        )
        SELECT
            u.symbol, u.yahoo_symbol, u.name, u.full_name, u.country, u.market,
            u.exchange, u.exchange_mic, u.isin, u.currency, u.source,
            u.source_url, u.is_active, u.refreshed_at,
            coalesce(
                s.last_attempted_at,
                CASE WHEN ? = 'analysis'
                     THEN analysis_history.last_attempted_at
                     ELSE content_history.last_attempted_at END
            ) AS last_attempted_at,
            s.last_succeeded_at, s.last_error
        FROM stock_universe u
        LEFT JOIN stock_update_status s
          ON s.update_type = ?
         AND s.country = lower(u.country)
         AND s.ticker = upper(u.symbol)
        LEFT JOIN analysis_history
          ON analysis_history.country = lower(u.country)
         AND analysis_history.ticker = upper(u.symbol)
        LEFT JOIN content_history
          ON content_history.country = lower(u.country)
         AND content_history.ticker = upper(u.symbol)
        WHERE {' AND '.join(conditions)}
        ORDER BY last_attempted_at ASC NULLS FIRST,
                 lower(u.country), upper(u.symbol)
        {limit_clause}
        """,
        params,
        db_path,
    )


def query_stock_analysis_queue(
    countries: Iterable[str] | str | None = None,
    *,
    limit: int | None = None,
    minimum_success_age_hours: float | None = 24.0,
    db_path: Path | None = None,
) -> pd.DataFrame:
    return _query_stale_stock_queue(
        update_type="analysis", countries=countries, limit=limit,
        minimum_success_age_hours=minimum_success_age_hours, db_path=db_path
    )


def query_stock_content_queue(
    countries: Iterable[str] | str | None = None,
    *,
    limit: int | None = 100,
    db_path: Path | None = None,
) -> pd.DataFrame:
    """Return never-attempted stocks first, then least recently attempted."""
    return _query_stale_stock_queue(
        update_type="content", countries=countries, limit=limit,
        minimum_success_age_hours=None, db_path=db_path
    )


def _append_unseen_records(
    frame: pd.DataFrame,
    *,
    table: str,
    columns: list[str],
    column_types: dict[str, str] | None = None,
    db_path: Path | None = None,
) -> int:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return 0
    con = init_db(db_path)
    data = frame.copy()
    for column in columns:
        if column not in data.columns:
            data[column] = None
    data = data[columns].drop_duplicates("record_hash", keep="last")
    if table == "financial_statement_landing":
        data["value"] = pd.to_numeric(data["value"], errors="coerce")
    con.register("new_records", data, column_types=column_types)
    inserted = con.execute(
        f"""
        INSERT INTO {table} ({', '.join(columns)})
        SELECT {', '.join('n.' + column for column in columns)}
        FROM new_records n
        WHERE NOT EXISTS (
            SELECT 1 FROM {table} current
            WHERE current.record_hash = n.record_hash
        )
        RETURNING record_hash
        """
    ).fetchall()
    con.unregister("new_records")
    con.close()
    return len(inserted)


def save_news_articles(frame: pd.DataFrame, db_path: Path | None = None) -> int:
    return _append_unseen_records(
        frame,
        table="news_article_landing",
        columns=[
            "article_id", "provider_article_id", "ticker", "yahoo_symbol", "country",
            "provider", "published_at", "title", "publisher", "summary", "url",
            "content_type", "raw_payload_json", "fetched_at", "record_hash",
        ],
        column_types=_NEWS_COLUMN_TYPES,
        db_path=db_path,
    )


def save_financial_statements(frame: pd.DataFrame, db_path: Path | None = None) -> int:
    return _append_unseen_records(
        frame,
        table="financial_statement_landing",
        columns=[
            "ticker", "yahoo_symbol", "country", "provider", "statement_type",
            "period_type", "fiscal_period_end", "line_item", "line_item_label", "value",
            "currency", "reported_at", "fetched_at", "record_hash", "raw_payload_json",
        ],
        column_types=_FINANCIAL_STATEMENT_COLUMN_TYPES,
        db_path=db_path,
    )


def _table_exists(con: Any, schema: str, table: str) -> bool:
    return bool(
        con.execute(
            """
            SELECT count(*) FROM information_schema.tables
            WHERE table_schema = ? AND table_name = ?
            """,
            [schema, table],
        ).fetchone()[0]
    )


def query_stock_news(
    ticker: str,
    country: str,
    *,
    limit: int = 30,
    db_path: Path | None = None,
) -> pd.DataFrame:
    con = init_db(db_path)
    try:
        if _table_exists(con, "gold", "fact_stock_news"):
            relation = "gold.fact_stock_news"
        else:
            relation = "news_article_landing"
        return con.execute(
            f"""
            SELECT article_id, provider_article_id, ticker, yahoo_symbol, country,
                   provider, published_at, title, publisher, summary, url,
                   content_type, fetched_at
            FROM (
                SELECT *, row_number() OVER (
                    PARTITION BY article_id, upper(ticker), lower(country)
                    ORDER BY fetched_at DESC
                ) AS article_rank
                FROM {relation}
                WHERE upper(ticker) = upper(?) AND lower(country) = lower(?)
            ) ranked
            WHERE article_rank = 1
            ORDER BY published_at DESC NULLS LAST, fetched_at DESC
            LIMIT ?
            """,
            [ticker, country, limit],
        ).df()
    finally:
        con.close()


def query_fundamental_trends(
    ticker: str,
    country: str,
    *,
    period_type: str | None = None,
    db_path: Path | None = None,
) -> pd.DataFrame:
    con = init_db(db_path)
    try:
        if not _table_exists(con, "gold", "fact_fundamental_trend"):
            return pd.DataFrame()
        conditions = ["upper(ticker) = upper(?)", "lower(country) = lower(?)"]
        params: list[Any] = [ticker, country]
        if period_type:
            conditions.append("period_type = ?")
            params.append(period_type.lower())
        return con.execute(
            f"""
            SELECT * FROM gold.fact_fundamental_trend
            WHERE {' AND '.join(conditions)}
            ORDER BY fiscal_period_end DESC, statement_type, line_item
            """,
            params,
        ).df()
    finally:
        con.close()


def query_financial_statement_trends(
    ticker: str,
    country: str,
    *,
    period_type: str,
    db_path: Path | None = None,
) -> pd.DataFrame:
    frame = query_fundamental_trends(
        ticker, country, period_type=period_type, db_path=db_path
    )
    if frame.empty:
        return frame
    frame = frame.rename(columns={
        "line_item": "canonical_line_item",
        "period_change_ratio": "period_change_pct",
        "year_over_year_change_ratio": "year_over_year_pct",
    })
    for column in ("period_change_pct", "year_over_year_pct"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce") * 100.0
    return frame
