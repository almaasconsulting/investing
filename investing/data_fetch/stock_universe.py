from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from typing import Iterable
from urllib.request import Request, urlopen

import pandas as pd

from investing.data_fetch.investing_com import resolve_yahoo_symbol

EURONEXT_OSLO_DOWNLOAD_URL = (
    "https://live.euronext.com/product_directory/data/stocks-oslo/download"
    "?mics=MERK%2CXOAS%2CXOSL"
)

OSLO_MARKET_MIC_BY_NAME = {
    "Oslo B\u00f8rs": "XOSL",
    "Euronext Growth Oslo": "MERK",
    "Euronext Expand Oslo": "XOAS",
}

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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _column(df: pd.DataFrame, column: str, default: str = "") -> pd.Series:
    if column in df.columns:
        return df[column].fillna(default).astype(str).str.strip()
    return pd.Series([default] * len(df), index=df.index)


def _empty_universe() -> pd.DataFrame:
    return pd.DataFrame(columns=STOCK_UNIVERSE_COLUMNS)


def _download_text(url: str, timeout: int = 30) -> str:
    request = Request(
        url,
        headers={
            "Accept": "text/csv,*/*",
            "User-Agent": "investing-analysis/1.0",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8-sig"
        payload = response.read()
        try:
            return payload.decode(charset)
        except UnicodeDecodeError:
            return payload.decode("latin-1")


def _read_euronext_download(text: str) -> pd.DataFrame:
    lines = text.lstrip("\ufeff").splitlines()
    if not lines:
        return pd.DataFrame()

    header = lines[0]
    table_lines = [header]
    table_lines.extend(line for line in lines[1:] if line.count(";") >= 4)
    if len(table_lines) == 1:
        return pd.DataFrame()

    return pd.read_csv(
        StringIO("\n".join(table_lines)),
        sep=";",
        dtype=str,
        keep_default_na=False,
    )


def fetch_euronext_oslo_stock_universe(url: str = EURONEXT_OSLO_DOWNLOAD_URL) -> pd.DataFrame:
    """Fetch current Oslo equity listings from Euronext's official product directory."""
    raw = _read_euronext_download(_download_text(url))
    if raw.empty:
        return _empty_universe()

    refreshed_at = _utc_now()
    market = _column(raw, "Market")
    name = _column(raw, "Name")
    symbol = _column(raw, "Symbol").str.upper()
    universe = pd.DataFrame(
        {
            "symbol": symbol,
            "yahoo_symbol": symbol.map(lambda value: resolve_yahoo_symbol(value, "norway")),
            "name": name,
            "full_name": name,
            "country": "norway",
            "market": market,
            "exchange": market,
            "exchange_mic": market.map(OSLO_MARKET_MIC_BY_NAME).fillna(""),
            "isin": _column(raw, "ISIN"),
            "currency": _column(raw, "Currency").str.upper(),
            "source": "euronext",
            "source_url": url,
            "is_active": True,
            "refreshed_at": refreshed_at,
        }
    )
    return universe[universe["symbol"] != ""].reset_index(drop=True)


def fetch_investpy_stock_universe(country: str) -> pd.DataFrame:
    """Fetch stock metadata from investpy's packaged stocks.csv fallback."""
    import investpy

    country = country.strip().lower()
    raw = investpy.get_stocks(country=country)
    if raw.empty:
        return _empty_universe()

    refreshed_at = _utc_now()
    symbol = _column(raw, "symbol").str.upper()
    country_values = _column(raw, "country", country).str.lower()
    name = _column(raw, "name")
    full_name = _column(raw, "full_name")
    full_name = full_name.mask(full_name == "", name)
    universe = pd.DataFrame(
        {
            "symbol": symbol,
            "yahoo_symbol": [
                resolve_yahoo_symbol(stock_symbol, stock_country)
                for stock_symbol, stock_country in zip(symbol, country_values)
            ],
            "name": name,
            "full_name": full_name,
            "country": country_values,
            "market": "",
            "exchange": "",
            "exchange_mic": "",
            "isin": _column(raw, "isin"),
            "currency": _column(raw, "currency").str.upper(),
            "source": "investpy",
            "source_url": "investpy.resources.stocks.csv",
            "is_active": True,
            "refreshed_at": refreshed_at,
        }
    )
    return universe[universe["symbol"] != ""].reset_index(drop=True)


def _normalize_countries(countries: Iterable[str] | str | None) -> list[str]:
    if countries is None:
        return ["norway"]
    if isinstance(countries, str):
        countries = countries.split(",")
    values = [country.strip().lower() for country in countries if country and country.strip()]
    return values or ["norway"]


def fetch_stock_universe(
    countries: Iterable[str] | str | None = None,
    source: str = "auto",
) -> pd.DataFrame:
    """
    Fetch stock-universe metadata for one or more countries.

    Norway uses Euronext's live Oslo product directory in auto mode. Other
    countries use investpy's packaged stock list.
    """
    source = source.strip().lower()
    frames: list[pd.DataFrame] = []

    for country in _normalize_countries(countries):
        if source == "euronext":
            if country != "norway":
                raise ValueError("The Euronext source currently supports only Norway.")
            frames.append(fetch_euronext_oslo_stock_universe())
            continue

        if source == "investpy":
            frames.append(fetch_investpy_stock_universe(country))
            continue

        if source != "auto":
            raise ValueError("Universe source must be one of: auto, euronext, investpy.")

        if country == "norway":
            try:
                frames.append(fetch_euronext_oslo_stock_universe())
            except Exception:
                frames.append(fetch_investpy_stock_universe(country))
        else:
            frames.append(fetch_investpy_stock_universe(country))

    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return _empty_universe()
    return pd.concat(frames, ignore_index=True)[STOCK_UNIVERSE_COLUMNS]
