from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb
import pandas as pd

DB_FILENAME = "data/investing.duckdb"
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


def get_db_path() -> Path:
    path = Path(__file__).resolve().parents[1] / DB_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def init_db(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = db_path or get_db_path()
    con = duckdb.connect(str(path))
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
            signal_summary VARCHAR
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
            altman_z_zone VARCHAR
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
        """
    )
    con.execute("ALTER TABLE stock_history ADD COLUMN IF NOT EXISTS data_source VARCHAR;")
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
    con.execute("ALTER TABLE stock_universe ADD COLUMN IF NOT EXISTS yahoo_symbol VARCHAR;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS run_timestamp TIMESTAMP;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS yahoo_symbol VARCHAR;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS universe_market VARCHAR;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS universe_isin VARCHAR;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS days INTEGER;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS min_score DOUBLE;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS max_volatility DOUBLE;")
    con.execute("ALTER TABLE analysis_snapshot ADD COLUMN IF NOT EXISTS notes VARCHAR;")
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


def _to_json(value: Any) -> str:
    return json.dumps(value or {}, default=_json_default, sort_keys=True)


def _from_json(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


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

    for column in ["ma20", "ma50", "ma200", "rsi14", "direction", "signal_summary"]:
        if column not in df.columns:
            df[column] = None

    con.register("new_data", df)
    con.execute(
        """
        INSERT INTO stock_history (date, ticker, name, country, exchange, data_source, open, high, low, close, volume, ma20, ma50, ma200, rsi14, direction, signal_summary)
        SELECT date, ticker, name, country, exchange, data_source, open, high, low, close, volume, ma20, ma50, ma200, rsi14, direction, signal_summary
        FROM new_data
        """
    )
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
) -> None:
    con = init_db(db_path)
    snapshot_date = snapshot_date or date.today()
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
    }
    df = pd.DataFrame([row])
    con.register("new_data", df)
    con.execute(
        """
        INSERT INTO fundamental_snapshot (
            snapshot_date, ticker, name, country, exchange, data_source, market_cap,
            pe_ratio, eps, dividend_yield, beta, one_year_change, shares_outstanding,
            revenue, prev_close, sector, industry, revenue_growth, earnings_growth,
            return_on_equity, profit_margins, debt_to_equity, current_ratio, free_cashflow,
            altman_z_score, altman_z_zone
        )
        SELECT
            snapshot_date, ticker, name, country, exchange, data_source, market_cap,
            pe_ratio, eps, dividend_yield, beta, one_year_change, shares_outstanding,
            revenue, prev_close, sector, industry, revenue_growth, earnings_growth,
            return_on_equity, profit_margins, debt_to_equity, current_ratio, free_cashflow,
            altman_z_score, altman_z_zone
        FROM new_data
        """
    )
    con.unregister("new_data")
    con.close()


def query_stock_history(ticker: str, country: str = "norway", db_path: Path | None = None) -> pd.DataFrame:
    con = init_db(db_path)
    query = """
        SELECT DISTINCT *
        FROM stock_history
        WHERE (LOWER(ticker) = ? OR LOWER(name) = ?)
          AND LOWER(country) = ?
        ORDER BY date
    """
    df = con.execute(query, [ticker.lower(), ticker.lower(), country.lower()]).df()
    con.close()
    return df


def query_fundamental_snapshots(ticker: str, country: str = "norway", db_path: Path | None = None) -> pd.DataFrame:
    con = init_db(db_path)
    query = """
        SELECT *
        FROM fundamental_snapshot
        WHERE (LOWER(ticker) = ? OR LOWER(name) = ?)
          AND LOWER(country) = ?
        ORDER BY snapshot_date
    """
    df = con.execute(query, [ticker.lower(), ticker.lower(), country.lower()]).df()
    con.close()
    return df


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
    con.register("new_analysis_snapshot", df)
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
    con = init_db(db_path)
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
    df = con.execute(
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
    ).df()
    con.close()

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
    if countries:
        placeholders = ",".join("?" for _ in countries)
        con.execute(
            f"DELETE FROM stock_universe WHERE LOWER(country) IN ({placeholders})",
            [country.lower() for country in countries],
        )

    con.register("new_stock_universe", df)
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
    con = init_db(db_path)
    conditions: list[str] = []
    params: list[str] = []

    if active_only:
        conditions.append("is_active")

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

    market_values = _coerce_filter_values(markets)
    if market_values:
        lower_placeholders = ",".join("?" for _ in market_values)
        upper_placeholders = ",".join("?" for _ in market_values)
        conditions.append(
            f"""(
                LOWER(market) IN ({lower_placeholders})
                OR LOWER(exchange) IN ({lower_placeholders})
                OR UPPER(exchange_mic) IN ({upper_placeholders})
            )"""
        )
        params.extend(market.lower() for market in market_values)
        params.extend(market.lower() for market in market_values)
        params.extend(market.upper() for market in market_values)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    df = con.execute(
        f"""
        SELECT
            symbol, yahoo_symbol, name, full_name, country, market, exchange, exchange_mic,
            isin, currency, source, source_url, is_active, refreshed_at
        FROM stock_universe
        {where_clause}
        ORDER BY country, market, symbol
        """,
        params,
    ).df()
    con.close()
    return df


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
