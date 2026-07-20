from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from typing import Iterable
from urllib.request import Request, urlopen

import pandas as pd
import yfinance as yf
from yfinance import EquityQuery

from investing.data_fetch.investing_com import resolve_yahoo_symbol


STOCK_UNIVERSE_COLUMNS = [
    "symbol", "yahoo_symbol", "name", "full_name", "country", "market",
    "exchange", "exchange_mic", "isin", "currency", "source", "source_url",
    "is_active", "refreshed_at",
]


@dataclass(frozen=True)
class ConstituentSource:
    name: str
    url: str
    minimum_rows: int


# Public constituent tables are used as operational mirrors. The index names
# and membership policies remain those of the corresponding index providers.
FLAGSHIP_INDEX_BY_COUNTRY = {
    "united states": ConstituentSource(
        "S&P 500", "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", 450
    ),
    "canada": ConstituentSource(
        "S&P/TSX 60", "https://en.wikipedia.org/wiki/S%26P/TSX_60", 50
    ),
    "united kingdom": ConstituentSource(
        "FTSE 100", "https://en.wikipedia.org/wiki/FTSE_100_Index", 90
    ),
    "france": ConstituentSource(
        "CAC 40", "https://en.wikipedia.org/wiki/CAC_40", 35
    ),
    "germany": ConstituentSource(
        "DAX 40", "https://en.wikipedia.org/wiki/DAX", 35
    ),
    "switzerland": ConstituentSource(
        "SMI", "https://en.wikipedia.org/wiki/Swiss_Market_Index", 18
    ),
    "sweden": ConstituentSource(
        "OMX Stockholm 30", "https://en.wikipedia.org/wiki/OMX_Stockholm_30", 25
    ),
    "netherlands": ConstituentSource(
        "AEX", "https://en.wikipedia.org/wiki/AEX_index", 20
    ),
    "italy": ConstituentSource(
        "FTSE MIB", "https://en.wikipedia.org/wiki/FTSE_MIB", 35
    ),
    "spain": ConstituentSource(
        "IBEX 35", "https://en.wikipedia.org/wiki/IBEX_35", 30
    ),
    "denmark": ConstituentSource(
        "OMX Copenhagen 25", "https://en.wikipedia.org/wiki/OMX_Copenhagen_25", 20
    ),
    "finland": ConstituentSource(
        "OMX Helsinki 25", "https://en.wikipedia.org/wiki/OMX_Helsinki_25", 20
    ),
}

DIVIDEND_ARISTOCRAT_SOURCES = {
    "united states": (
        ConstituentSource(
            "US Dividend Aristocrats",
            "https://en.wikipedia.org/wiki/S%26P_500_Dividend_Aristocrats",
            40,
        ),
    ),
    "canada": (
        ConstituentSource(
            "Canadian Dividend Aristocrats",
            "https://www.blackrock.com/ca/investors/en/products/239834/"
            "ishares-sptsx-canadian-dividend-aristocrats-index-fund",
            40,
        ),
        ConstituentSource(
            "Canadian Dividend Aristocrats",
            "https://wealthnorth.ca/investing/dividend-aristocrats-canada/",
            40,
        ),
    ),
}

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

DEFAULT_CURRENCY_BY_COUNTRY = {
    "norway": "NOK", "united states": "USD", "canada": "CAD",
    "united kingdom": "GBP", "france": "EUR", "germany": "EUR",
    "switzerland": "CHF", "sweden": "SEK", "netherlands": "EUR",
    "italy": "EUR", "spain": "EUR", "denmark": "DKK", "finland": "EUR",
}

YAHOO_EXCHANGES_BY_COUNTRY = {
    "united states": ("NYQ", "NMS", "NCM", "NGM", "ASE"),
    "canada": ("TOR",),
}

YAHOO_TO_MIC = {
    "NYQ": "XNYS", "NMS": "XNAS", "NCM": "XNAS", "NGM": "XNAS",
    "ASE": "XASE", "TOR": "XTSE",
}

REIT_INDUSTRIES = (
    "REIT—Diversified", "REIT—Healthcare Facilities", "REIT—Hotel & Motel",
    "REIT—Industrial", "REIT—Mortgage", "REIT—Office", "REIT—Residential",
    "REIT—Retail", "REIT—Specialty",
)

SYMBOL_COLUMN_NAMES = {
    "symbol", "ticker", "ticker symbol", "ticker (yahoo)", "epic", "code",
    "exchange ticker", "yahoo ticker",
}
NAME_COLUMN_NAMES = {
    "company", "company name", "constituent", "security", "name",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _download_text(url: str, timeout: int = 45) -> str:
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,*/*",
            "User-Agent": "Mozilla/5.0 investing-index-universe/1.0",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        payload = response.read()
        try:
            return payload.decode(charset)
        except UnicodeDecodeError:
            return payload.decode("utf-8", errors="replace")


def _header_name(value: object) -> str:
    if isinstance(value, tuple):
        parts = [str(part) for part in value if not str(part).startswith("Unnamed")]
        value = " ".join(parts)
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def _find_column(frame: pd.DataFrame, candidates: set[str]) -> object | None:
    normalized = {column: _header_name(column) for column in frame.columns}
    for column, name in normalized.items():
        if name in candidates:
            return column
    for column, name in normalized.items():
        if any(candidate in name for candidate in candidates):
            return column
    return None


def _constituent_table(html: str, minimum_rows: int) -> tuple[pd.DataFrame, object, object | None]:
    candidates: list[tuple[pd.DataFrame, object, object | None]] = []
    for frame in pd.read_html(StringIO(html)):
        symbol_column = _find_column(frame, SYMBOL_COLUMN_NAMES)
        if symbol_column is None:
            continue
        name_column = _find_column(frame, NAME_COLUMN_NAMES)
        candidates.append((frame, symbol_column, name_column))
    if not candidates:
        raise ValueError("No constituent table with a ticker/symbol column was found.")
    frame, symbol_column, name_column = max(candidates, key=lambda item: len(item[0]))
    if len(frame) < minimum_rows:
        raise ValueError(
            f"Constituent table contained {len(frame)} rows; expected at least {minimum_rows}."
        )
    return frame, symbol_column, name_column


def _clean_symbol(value: object, country: str) -> str:
    symbol = re.sub(r"\[[^]]*]", "", str(value)).strip().upper()
    symbol = symbol.splitlines()[0].strip()
    if ":" in symbol:
        symbol = symbol.rsplit(":", 1)[-1].strip()
    symbol = re.sub(r"\s+", "-", symbol)
    if country in {"united states", "canada", "united kingdom"}:
        symbol = symbol.replace(".", "-")
    return re.sub(r"[^A-Z0-9-]", "", symbol)


def _index_rows(source: ConstituentSource, country: str) -> pd.DataFrame:
    frame, symbol_column, name_column = _constituent_table(
        _download_text(source.url), source.minimum_rows
    )
    exchange, mic = PRIMARY_MARKET_BY_COUNTRY[country]
    refreshed_at = _utc_now()
    rows: list[dict] = []
    for _, row in frame.iterrows():
        symbol = _clean_symbol(row.get(symbol_column, ""), country)
        if not symbol or symbol in {"NAN", "NONE"}:
            continue
        name_value = row.get(name_column, symbol) if name_column is not None else symbol
        name = re.sub(r"\[[^]]*]", "", str(name_value)).strip() or symbol
        rows.append(
            {
                "symbol": symbol,
                "yahoo_symbol": resolve_yahoo_symbol(symbol, country),
                "name": name,
                "full_name": name,
                "country": country,
                "market": source.name,
                "exchange": exchange,
                "exchange_mic": mic,
                "isin": "",
                "currency": DEFAULT_CURRENCY_BY_COUNTRY[country],
                "source": "index_constituent",
                "source_url": source.url,
                "is_active": True,
                "refreshed_at": refreshed_at,
            }
        )
    result = pd.DataFrame(rows, columns=STOCK_UNIVERSE_COLUMNS)
    if len(result) < source.minimum_rows:
        raise ValueError(
            f"{source.name} produced {len(result)} valid symbols; expected at least "
            f"{source.minimum_rows}."
        )
    return result


def fetch_flagship_index_universe(country: str) -> pd.DataFrame:
    try:
        source = FLAGSHIP_INDEX_BY_COUNTRY[country]
    except KeyError as exc:
        raise ValueError(f"No flagship index is configured for {country!r}.") from exc
    return _index_rows(source, country)


def fetch_dividend_aristocrats(country: str) -> pd.DataFrame:
    errors: list[str] = []
    for source in DIVIDEND_ARISTOCRAT_SOURCES.get(country, ()):
        try:
            return _index_rows(source, country).assign(source="dividend_aristocrat")
        except Exception as exc:
            errors.append(f"{source.url}: {exc}")
    if errors:
        raise RuntimeError(
            f"Unable to fetch {country} dividend aristocrats: {'; '.join(errors)}"
        )
    return pd.DataFrame(columns=STOCK_UNIVERSE_COLUMNS)


def _screen_quotes(query: EquityQuery, page_size: int = 250) -> list[dict]:
    quotes: list[dict] = []
    offset = 0
    while True:
        response = yf.screen(
            query, offset=offset, size=page_size, sortField="ticker", sortAsc=True
        )
        page = response.get("quotes", [])
        if not page:
            break
        quotes.extend(page)
        offset += len(page)
        if len(page) < page_size or offset >= int(response.get("total", offset) or offset):
            break
    return quotes


def fetch_reit_universe(country: str) -> pd.DataFrame:
    exchanges = YAHOO_EXCHANGES_BY_COUNTRY[country]
    query = EquityQuery(
        "and",
        [
            EquityQuery("is-in", ["exchange", *exchanges]),
            EquityQuery("is-in", ["industry", *REIT_INDUSTRIES]),
        ],
    )
    refreshed_at = _utc_now()
    rows: list[dict] = []
    for quote in _screen_quotes(query):
        yahoo_symbol = str(quote.get("symbol") or "").strip().upper()
        if not yahoo_symbol:
            continue
        symbol = yahoo_symbol
        suffix = ".TO" if country == "canada" else ""
        if suffix and symbol.endswith(suffix):
            symbol = symbol[: -len(suffix)]
        symbol = symbol.replace("-", ".") if country == "canada" else symbol
        name = str(quote.get("shortName") or quote.get("longName") or symbol).strip()
        exchange_code = str(quote.get("exchange") or "").upper()
        rows.append(
            {
                "symbol": symbol,
                "yahoo_symbol": yahoo_symbol,
                "name": name,
                "full_name": str(quote.get("longName") or name),
                "country": country,
                "market": "US REITs" if country == "united states" else "Canadian REITs",
                "exchange": str(quote.get("fullExchangeName") or exchange_code),
                "exchange_mic": YAHOO_TO_MIC.get(exchange_code, exchange_code),
                "isin": "",
                "currency": str(quote.get("currency") or DEFAULT_CURRENCY_BY_COUNTRY[country]).upper(),
                "source": "reit_screener",
                "source_url": "https://finance.yahoo.com/research-hub/screener/equity/",
                "is_active": True,
                "refreshed_at": refreshed_at,
            }
        )
    result = pd.DataFrame(rows, columns=STOCK_UNIVERSE_COLUMNS)
    if len(result) < 10:
        raise RuntimeError(
            f"Yahoo REIT screen returned only {len(result)} {country} rows; "
            "the previous curated universe was left unchanged."
        )
    return result


def fetch_curated_index_universe(countries: Iterable[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    warnings: list[str] = []
    for country in countries:
        country_frames = [fetch_flagship_index_universe(country)]
        if country in {"united states", "canada"}:
            for label, fetcher in (
                ("REIT", fetch_reit_universe),
                ("dividend aristocrat", fetch_dividend_aristocrats),
            ):
                try:
                    extra = fetcher(country)
                    if not extra.empty:
                        country_frames.append(extra)
                except Exception as exc:
                    warnings.append(f"{country} {label} enrichment skipped: {exc}")
        country_frame = pd.concat(country_frames, ignore_index=True)
        country_frame = country_frame.drop_duplicates(
            ["country", "yahoo_symbol"], keep="first"
        )
        frames.append(country_frame)
    if not frames:
        result = pd.DataFrame(columns=STOCK_UNIVERSE_COLUMNS)
    else:
        result = pd.concat(frames, ignore_index=True)[STOCK_UNIVERSE_COLUMNS]
    result.attrs["warnings"] = warnings
    return result
