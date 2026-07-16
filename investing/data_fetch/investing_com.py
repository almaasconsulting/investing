from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

import pandas as pd
import yfinance as yf


def _load_investpy() -> Any:
    try:
        import investpy
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Investing.com support requires investpy and setuptools. "
            "Run: python -m pip install -r requirements.txt"
        ) from exc
    return investpy


def find_stock(symbol: str, country: str = "norway") -> Optional[Any]:
    """Search Investing.com stocks by symbol or name."""
    investpy = _load_investpy()
    query = symbol.strip()
    results = investpy.search_quotes(text=query, products=["stocks"], countries=[country], n_results=10)
    if not results:
        return None

    for quote in results:
        if quote.symbol.lower() == query.lower() or quote.name.lower() == query.lower():
            return quote

    return results[0]


def search_stocks(query: str, country: str = "norway", n_results: int = 20) -> list[Any]:
    """Return stock matches for a text query and country."""
    query_text = query.strip()
    if not query_text:
        return []

    investpy = _load_investpy()
    return list(investpy.search_quotes(text=query_text, products=["stocks"], countries=[country], n_results=n_results))


def resolve_yahoo_symbol(symbol: str, country: str = "norway") -> str:
    mapping = {
        "norway": ".OL",
        "sweden": ".ST",
        "denmark": ".CO",
        "finland": ".HE",
        "netherlands": ".AS",
        "spain": ".MC",
        "italy": ".MI",
        "germany": ".DE",
        "france": ".PA",
        "uk": ".L",
    }
    symbol = symbol.strip()
    if "." in symbol:
        return symbol
    suffix = mapping.get(country.lower())
    return f"{symbol}{suffix}" if suffix else symbol


def _resolve_yahoo_symbol(symbol: str, country: str = "norway") -> str:
    return resolve_yahoo_symbol(symbol, country)


def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if "Date" in df.columns:
        df = df.rename(columns={"Date": "date"})
    else:
        df = df.reset_index()
        if "Date" in df.columns:
            df = df.rename(columns={"Date": "date"})
        elif df.index.name == "date":
            df = df.rename(columns={"date": "date"})

    if "date" not in df.columns:
        df["date"] = pd.to_datetime(df.index)

    df["date"] = pd.to_datetime(df["date"])
    df = df.rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Volume": "volume",
    })

    if "Adj Close" in df.columns:
        df["close"] = df["Adj Close"]
    elif "Close" in df.columns:
        df["close"] = df["Close"]

    if "close" not in df.columns:
        raise ValueError("Missing expected data column: close")

    expected = ["date", "open", "high", "low", "close", "volume"]
    missing = [col for col in expected if col not in df.columns]
    if missing:
        raise ValueError(f"Missing expected data columns: {missing}")
    return df[expected]


def _get_stock_data_yahoo(symbol: str, country: str, days: int) -> pd.DataFrame:
    ticker_symbol = _resolve_yahoo_symbol(symbol, country)
    ticker = yf.Ticker(ticker_symbol)
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    df = ticker.history(start=start_date, end=end_date + timedelta(days=1), interval="1d", auto_adjust=False)
    if df.empty:
        raise ValueError(f"No Yahoo Finance data returned for {symbol} ({country})")
    return _normalize_df(df)


def _get_stock_data_investing(symbol: str, country: str, days: int) -> pd.DataFrame:
    stock = find_stock(symbol, country)
    if stock is None:
        raise ValueError(f"No stock found for symbol '{symbol}' in country '{country}'")

    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    from_date = start_date.strftime("%d/%m/%Y")
    to_date = end_date.strftime("%d/%m/%Y")

    df = stock.retrieve_historical_data(from_date=from_date, to_date=to_date)
    if df.empty:
        raise ValueError(f"No historical data returned for {symbol} ({country})")

    df.index = pd.to_datetime(df.index)
    df = df.rename(columns={
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    })
    df = df[["open", "high", "low", "close", "volume"]].reset_index().rename(columns={"Date": "date"})
    return df


def _prepare_history_for_merge(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    dates = pd.to_datetime(prepared["date"])
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    prepared["date"] = dates.dt.normalize()
    return prepared.drop_duplicates("date", keep="last").set_index("date").sort_index()


def merge_stock_histories(yahoo: pd.DataFrame, investing: pd.DataFrame) -> pd.DataFrame:
    """Merge daily OHLCV histories, preferring Yahoo values on each date."""
    yahoo_prepared = _prepare_history_for_merge(yahoo)
    investing_prepared = _prepare_history_for_merge(investing)
    dates = yahoo_prepared.index.union(investing_prepared.index).sort_values()
    merged = pd.DataFrame(index=dates)
    value_columns = ["open", "high", "low", "close", "volume"]
    for column in value_columns:
        yahoo_values = yahoo_prepared[column].reindex(dates)
        investing_values = investing_prepared[column].reindex(dates)
        merged[column] = yahoo_values.combine_first(investing_values)
        merged[f"yahoo_{column}"] = yahoo_values
        merged[f"investing_{column}"] = investing_values

    yahoo_values = yahoo_prepared.reindex(dates)[value_columns]
    investing_values = investing_prepared.reindex(dates)[value_columns]
    yahoo_contributed = yahoo_values.notna().any(axis=1)
    investing_filled_gap = (yahoo_values.isna() & investing_values.notna()).any(axis=1)
    merged["price_source"] = [
        "yahoo+investing" if has_yahoo and filled_gap else "yahoo" if has_yahoo else "investing"
        for has_yahoo, filled_gap in zip(yahoo_contributed, investing_filled_gap)
    ]
    merged = merged.reset_index(names="date")
    source_values = merged["price_source"].astype(str)
    providers_used = [
        provider
        for provider in ("yahoo", "investing")
        if source_values.str.contains(provider, regex=False).any()
    ]
    merged.attrs["data_source"] = "+".join(providers_used)
    merged.attrs["providers_used"] = providers_used
    return merged


def get_stock_data(
    symbol: str,
    country: str = "norway",
    days: int = 365,
    source: str = "auto",
) -> pd.DataFrame:
    """Fetch historical stock data for the given symbol and country."""
    source = source.strip().lower()
    if source not in {"auto", "investing", "yahoo"}:
        raise ValueError("Data source must be one of: auto, investing, yahoo.")

    if source == "yahoo":
        return _get_stock_data_yahoo(symbol, country, days)
    if source == "investing":
        return _get_stock_data_investing(symbol, country, days)

    yahoo_data = None
    investing_data = None
    yahoo_error = None
    investing_error = None
    try:
        yahoo_data = _get_stock_data_yahoo(symbol, country, days)
    except Exception as exc:
        yahoo_error = exc
    try:
        investing_data = _get_stock_data_investing(symbol, country, days)
    except Exception as exc:
        investing_error = exc

    if yahoo_data is not None and investing_data is not None:
        return merge_stock_histories(yahoo_data, investing_data)
    if yahoo_data is not None:
        yahoo_data.attrs["data_source"] = "yahoo"
        yahoo_data.attrs["providers_used"] = ["yahoo"]
        return yahoo_data
    if investing_data is not None:
        investing_data.attrs["data_source"] = "investing"
        investing_data.attrs["providers_used"] = ["investing"]
        return investing_data
    raise ValueError(
        f"No data returned for {symbol} ({country}). "
        f"Yahoo Finance error: {yahoo_error}. Investing.com error: {investing_error}"
    )
