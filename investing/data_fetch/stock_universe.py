from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from typing import Iterable
from urllib.request import Request, urlopen

import pandas as pd

from investing.data_fetch.investpy_compat import load_investpy
import yfinance as yf
from yfinance import EquityQuery

from investing.data_fetch.investing_com import resolve_yahoo_symbol
from investing.data_fetch.index_universe import fetch_curated_index_universe

EURONEXT_OSLO_DOWNLOAD_URL = (
    "https://live.euronext.com/product_directory/data/stocks-oslo/download"
    "?mics=MERK%2CXOAS%2CXOSL"
)

OSLO_MARKET_MIC_BY_NAME = {
    "Oslo B\u00f8rs": "XOSL",
    "Euronext Growth Oslo": "MERK",
    "Euronext Expand Oslo": "XOAS",
}

# The broad catalog intentionally uses one provider country per major market.
# Norway remains an additional home market and is not counted among the ten
# European exchanges below.
DEFAULT_MARKET_COUNTRIES = (
    "norway",
    "united states",
    "canada",
    "united kingdom",
    "france",
    "germany",
    "switzerland",
    "sweden",
    "netherlands",
    "italy",
    "spain",
    "denmark",
    "finland",
)

PRIMARY_MARKET_BY_COUNTRY = {
    "norway": ("Oslo Bors", "XOSL"),
    "united states": ("NYSE / Nasdaq", ""),
    "canada": ("Toronto Stock Exchange", "XTSE"),
    "united kingdom": ("London Stock Exchange", "XLON"),
    "france": ("Euronext Paris", "XPAR"),
    "germany": ("Deutsche Borse Xetra", "XETR"),
    "switzerland": ("SIX Swiss Exchange", "XSWX"),
    "sweden": ("Nasdaq Stockholm", "XSTO"),
    "netherlands": ("Euronext Amsterdam", "XAMS"),
    "italy": ("Borsa Italiana", "XMIL"),
    "spain": ("Bolsa de Madrid", "XMAD"),
    "denmark": ("Nasdaq Copenhagen", "XCSE"),
    "finland": ("Nasdaq Helsinki", "XHEL"),
}

YAHOO_EXCHANGES_BY_COUNTRY = {
    "norway": ("Oslo Exchange", ("OSL",)),
    "united states": ("US major exchanges", ("NYQ", "NMS", "NCM", "NGM", "ASE")),
    "canada": ("Toronto Stock Exchange", ("TOR",)),
    "united kingdom": ("London Stock Exchange", ("LSE",)),
    "france": ("Euronext Paris", ("PAR",)),
    "germany": ("Deutsche Borse Xetra", ("GER",)),
    "switzerland": ("SIX Swiss Exchange", ("EBS",)),
    "sweden": ("Nasdaq Stockholm", ("STO",)),
    "netherlands": ("Euronext Amsterdam", ("AMS",)),
    "italy": ("Borsa Italiana", ("MIL",)),
    "spain": ("Bolsa de Madrid", ("MAD",)),
    "denmark": ("Nasdaq Copenhagen", ("CPH",)),
    "finland": ("Nasdaq Helsinki", ("HEL",)),
}

YAHOO_TO_MIC = {
    "NYQ": "XNYS", "NMS": "XNAS", "NCM": "XNAS", "NGM": "XNAS", "ASE": "XASE",
    "TOR": "XTSE", "LSE": "XLON", "PAR": "XPAR", "GER": "XETR", "EBS": "XSWX",
    "STO": "XSTO", "AMS": "XAMS", "MIL": "XMIL", "MAD": "XMAD", "CPH": "XCSE",
    "HEL": "XHEL", "OSL": "XOSL",
}

COUNTRY_ALIASES = {
    "usa": "united states",
    "us": "united states",
    "united states of america": "united states",
    "uk": "united kingdom",
    "great britain": "united kingdom",
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
    investpy = load_investpy()

    country = COUNTRY_ALIASES.get(country.strip().lower(), country.strip().lower())
    raw = investpy.get_stocks(country=country)
    if raw.empty:
        return _empty_universe()

    refreshed_at = _utc_now()
    symbol = _column(raw, "symbol").str.upper()
    country_values = _column(raw, "country", country).str.lower()
    name = _column(raw, "name")
    full_name = _column(raw, "full_name")
    full_name = full_name.mask(full_name == "", name)
    primary_market, primary_mic = PRIMARY_MARKET_BY_COUNTRY.get(country, ("", ""))
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
            "market": primary_market,
            "exchange": primary_market,
            "exchange_mic": primary_mic,
            "isin": _column(raw, "isin"),
            "currency": _column(raw, "currency").str.upper(),
            "source": "investpy",
            "source_url": "investpy.resources.stocks.csv",
            "is_active": True,
            "refreshed_at": refreshed_at,
        }
    )
    return universe[universe["symbol"] != ""].reset_index(drop=True)


def _base_yahoo_symbol(symbol: str, country: str) -> str:
    suffixes = {
        "norway": (".OL",),
        "canada": (".TO",), "united kingdom": (".L",), "france": (".PA",),
        "germany": (".DE",), "switzerland": (".SW",), "sweden": (".ST",),
        "netherlands": (".AS",), "italy": (".MI",), "spain": (".MC",),
        "denmark": (".CO",), "finland": (".HE",),
    }
    for suffix in suffixes.get(country, ()):
        if symbol.upper().endswith(suffix):
            return symbol[:-len(suffix)]
    return symbol


def fetch_yahoo_exchange_stock_universe(country: str, page_size: int = 250) -> pd.DataFrame:
    """Fetch equities belonging to the configured exchange codes."""
    country = COUNTRY_ALIASES.get(country.strip().lower(), country.strip().lower())
    market, exchange_codes = YAHOO_EXCHANGES_BY_COUNTRY[country]
    query = EquityQuery("is-in", ["exchange", *exchange_codes])
    quotes: list[dict] = []
    offset = 0
    while True:
        response = yf.screen(query, offset=offset, size=page_size, sortField="ticker", sortAsc=True)
        page = response.get("quotes", [])
        if not page:
            break
        quotes.extend(page)
        offset += len(page)
        if len(page) < page_size or offset >= int(response.get("total", offset) or offset):
            break

    refreshed_at = _utc_now()
    rows: list[dict] = []
    for quote in quotes:
        if str(quote.get("quoteType", "EQUITY")).upper() != "EQUITY":
            continue
        yahoo_symbol = str(quote.get("symbol", "") or "").strip().upper()
        if not yahoo_symbol:
            continue
        exchange_code = str(quote.get("exchange", "") or "").upper()
        name = str(quote.get("shortName") or quote.get("longName") or yahoo_symbol)
        rows.append({
            "symbol": _base_yahoo_symbol(yahoo_symbol, country).upper(),
            "yahoo_symbol": yahoo_symbol,
            "name": name,
            "full_name": str(quote.get("longName") or name),
            "country": country,
            "market": market,
            "exchange": str(quote.get("fullExchangeName") or exchange_code),
            "exchange_mic": YAHOO_TO_MIC.get(exchange_code, exchange_code),
            "isin": "",
            "currency": str(quote.get("currency", "") or "").upper(),
            "source": "yahoo_screener",
            "source_url": "https://finance.yahoo.com/research-hub/screener/equity/",
            "is_active": True,
            "refreshed_at": refreshed_at,
        })
    return pd.DataFrame(rows, columns=STOCK_UNIVERSE_COLUMNS).drop_duplicates(
        ["country", "yahoo_symbol"], keep="last"
    ) if rows else _empty_universe()


def _normalize_countries(countries: Iterable[str] | str | None) -> list[str]:
    if countries is None:
        return list(DEFAULT_MARKET_COUNTRIES)
    if isinstance(countries, str):
        countries = countries.split(",")
    values = [
        COUNTRY_ALIASES.get(country.strip().lower(), country.strip().lower())
        for country in countries
        if country and country.strip()
    ]
    return list(dict.fromkeys(values)) or list(DEFAULT_MARKET_COUNTRIES)


def fetch_stock_universe(
    countries: Iterable[str] | str | None = None,
    source: str = "index",
) -> pd.DataFrame:
    """
    Fetch the curated flagship-index universe for one or more countries.

    United States and Canada also include REITs and their dividend-aristocrat
    collections. Exchange-wide discovery remains available only through the
    lower-level diagnostic functions in this module.
    """
    source = source.strip().lower()
    if source not in {"auto", "index"}:
        raise ValueError(
            "The application universe is index-only. Universe source must be 'index'."
        )
    normalized_countries = _normalize_countries(countries)
    universe = fetch_curated_index_universe(normalized_countries)
    missing = sorted(set(normalized_countries) - set(universe["country"].unique()))
    if missing:
        raise RuntimeError(
            "Curated universe refresh returned no constituents for: " + ", ".join(missing)
        )
    return universe[STOCK_UNIVERSE_COLUMNS]
