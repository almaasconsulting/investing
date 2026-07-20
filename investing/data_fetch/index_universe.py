from __future__ import annotations

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from io import StringIO
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
from yfinance import EquityQuery

from investing.data_fetch.investing_com import resolve_yahoo_symbol
from investing.data_fetch.investpy_compat import load_investpy


STOCK_UNIVERSE_COLUMNS = [
    "symbol", "yahoo_symbol", "name", "full_name", "country", "market",
    "exchange", "exchange_mic", "isin", "currency", "source", "source_url",
    "is_active", "refreshed_at",
]

INVESTING_INDEX_CATALOG_URLS = {
    "united states": "https://www.investing.com/indices/usa-indices",
    "canada": "https://www.investing.com/indices/canada-indices",
    "europe": "https://www.investing.com/indices/european-indices",
}

INVESTING_OSEBX_COMPONENTS_URL = (
    "https://www.investing.com/indices/ose-benchamrk-components"
)
EURONEXT_OSEBX_COMPOSITION_URL = (
    "https://live.euronext.com/en/ajax/"
    "getStockIndexCompositionBlockContent/NO0010865256-XOSL"
)

EUROPEAN_INDEX_COUNTRIES = {
    "united kingdom", "france", "germany", "switzerland", "sweden",
    "netherlands", "italy", "spain", "denmark", "finland",
}

INVESTING_COUNTRY_ALIASES = {
    "usa": "united states",
    "united states of america": "united states",
    "uk": "united kingdom",
    "great britain": "united kingdom",
}

_CATALOG_PATHS = {urlparse(url).path for url in INVESTING_INDEX_CATALOG_URLS.values()}


@dataclass(frozen=True)
class ConstituentSource:
    name: str
    url: str
    minimum_rows: int
    format: str = "html"


@dataclass(frozen=True)
class InvestingIndexEntry:
    name: str
    country: str
    components_url: str


# Public constituent tables are used as operational mirrors. The index names
# and membership policies remain those of the corresponding index providers.
MAJOR_INDEXES_BY_COUNTRY = {
    "norway": (
        ConstituentSource(
            "OSE Benchmark (OSEBX)",
            EURONEXT_OSEBX_COMPOSITION_URL,
            50,
        ),
    ),
    "united states": (
        ConstituentSource("S&P 500", "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", 450),
        ConstituentSource("Nasdaq-100", "https://en.wikipedia.org/wiki/Nasdaq-100", 90),
        ConstituentSource(
            "Russell 2000",
            "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/1467271812596.ajax?fileType=csv&fileName=IWM_holdings&dataType=fund",
            1500,
            "csv",
        ),
    ),
    "canada": (
        ConstituentSource("S&P/TSX 60", "https://en.wikipedia.org/wiki/S%26P/TSX_60", 50),
        ConstituentSource(
            "S&P/TSX Composite",
            "https://www.blackrock.com/ca/investors/en/products/239837/ishares-sptsx-capped-composite-index-etf/1464253357814.ajax?fileType=csv&fileName=XIC_holdings&dataType=fund",
            180,
            "csv",
        ),
    ),
    "united kingdom": (
        ConstituentSource("FTSE 100", "https://en.wikipedia.org/wiki/FTSE_100_Index", 90),
        ConstituentSource("FTSE 250", "https://en.wikipedia.org/wiki/FTSE_250_Index", 220),
    ),
    "france": (
        ConstituentSource("CAC 40", "https://en.wikipedia.org/wiki/CAC_40", 35),
        ConstituentSource("CAC Next 20", "https://en.wikipedia.org/wiki/CAC_Next_20", 15),
    ),
    "germany": (
        ConstituentSource("DAX 40", "https://en.wikipedia.org/wiki/DAX", 35),
        ConstituentSource(
            "MDAX",
            "https://www.blackrock.com/uk/individual/products/251845/ishares-mdax-ucits-etf-de-fund/1506575576011.ajax?fileType=csv&fileName=EXS3_holdings&dataType=fund",
            45,
            "csv",
        ),
    ),
    "switzerland": (ConstituentSource("SMI", "https://en.wikipedia.org/wiki/Swiss_Market_Index", 18),),
    "sweden": (ConstituentSource("OMX Stockholm 30", "https://en.wikipedia.org/wiki/OMX_Stockholm_30", 25),),
    "netherlands": (ConstituentSource("AEX", "https://en.wikipedia.org/wiki/AEX_index", 20),),
    "italy": (ConstituentSource("FTSE MIB", "https://en.wikipedia.org/wiki/FTSE_MIB", 35),),
    "spain": (ConstituentSource("IBEX 35", "https://en.wikipedia.org/wiki/IBEX_35", 30),),
    "denmark": (ConstituentSource("OMX Copenhagen 25", "https://en.wikipedia.org/wiki/OMX_Copenhagen_25", 20),),
    "finland": (ConstituentSource("OMX Helsinki 25", "https://en.wikipedia.org/wiki/OMX_Helsinki_25", 20),),
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
ISIN_COLUMN_NAMES = {"isin", "isin code"}
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


def _normalized_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _normalized_country(value: object) -> str:
    country = _normalized_text(value)
    return INVESTING_COUNTRY_ALIASES.get(country, country)


def _country_from_catalog_row(row: object, allowed_countries: set[str]) -> str | None:
    for element in row.find_all(True):
        for attribute in ("title", "data-country", "data-country-name"):
            value = element.get(attribute)
            if value:
                country = _normalized_country(value)
                if country in allowed_countries:
                    return country
    row_text = f" {_normalized_text(row.get_text(' ', strip=True))} "
    for country in sorted(allowed_countries, key=len, reverse=True):
        if f" {country} " in row_text:
            return country
    return None


def _parse_investing_index_catalog(
    html: str,
    *,
    allowed_countries: set[str],
    default_country: str | None = None,
) -> list[InvestingIndexEntry]:
    """Extract equity-index component links from an Investing.com catalog page."""
    soup = BeautifulSoup(html, "html.parser")
    entries: list[InvestingIndexEntry] = []
    seen: set[tuple[str, str]] = set()
    for anchor in soup.select('a[href*="/indices/"]'):
        href = str(anchor.get("href") or "").strip()
        path = urlparse(href).path.rstrip("/")
        if not path.startswith("/indices/") or path in _CATALOG_PATHS:
            continue
        if path.endswith(("-futures", "-historical-data", "-technical", "-chart")):
            continue
        row = anchor.find_parent("tr")
        if row is None:
            continue
        country = default_country or _country_from_catalog_row(row, allowed_countries)
        if country not in allowed_countries:
            continue
        name = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True)).strip()
        if not name:
            continue
        components_path = path if path.endswith("-components") else f"{path}-components"
        key = (country, components_path)
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            InvestingIndexEntry(
                name=name,
                country=country,
                components_url=urljoin("https://www.investing.com", components_path),
            )
        )
    return entries


def _investpy_stock_reference() -> pd.DataFrame:
    """Load Investing.com's packaged stock identifiers used by component rows."""
    load_investpy()
    resource = resources.files("investpy").joinpath("resources", "stocks.csv")
    with resources.as_file(resource) as path:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    for column in ("id", "tag", "name", "full_name", "symbol", "country"):
        if column not in frame.columns:
            frame[column] = ""
    frame["country"] = frame["country"].map(_normalized_country)
    return frame


def _component_stock_keys(row: object, anchor: object) -> tuple[str, str, str]:
    pair_id = ""
    for element in (row, anchor):
        for attribute in ("data-pair-id", "data-pair_id", "data-id", "id"):
            value = str(element.get(attribute) or "")
            match = re.search(r"(?:pair[_-])?(\d+)$", value)
            if match:
                pair_id = match.group(1)
                break
        if pair_id:
            break
    tag = urlparse(str(anchor.get("href") or "")).path.rstrip("/").rsplit("/", 1)[-1]
    name = _normalized_text(anchor.get_text(" ", strip=True))
    return pair_id, tag.lower(), name


def _fetch_investing_index_components(
    entry: InvestingIndexEntry,
    stock_reference: pd.DataFrame,
) -> pd.DataFrame:
    html = _download_text(entry.components_url, timeout=20)
    soup = BeautifulSoup(html, "html.parser")
    country_stocks = stock_reference[stock_reference["country"] == entry.country].copy()
    by_id = {str(value): row for value, (_, row) in zip(country_stocks["id"], country_stocks.iterrows())}
    by_tag = {str(value).lower(): row for value, (_, row) in zip(country_stocks["tag"], country_stocks.iterrows())}
    by_name: dict[str, pd.Series] = {}
    for _, stock in country_stocks.iterrows():
        for value in (stock["name"], stock["full_name"]):
            normalized = _normalized_text(value)
            if normalized:
                by_name.setdefault(normalized, stock)

    matches: list[pd.Series] = []
    seen_symbols: set[str] = set()
    for anchor in soup.select('a[href*="/equities/"]'):
        row = anchor.find_parent("tr")
        if row is None:
            continue
        pair_id, tag, name = _component_stock_keys(row, anchor)
        stock = by_id.get(pair_id)
        if stock is None:
            stock = by_tag.get(tag)
        if stock is None:
            stock = by_name.get(name)
        if stock is None:
            continue
        symbol = str(stock.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)
        matches.append(stock)

    if not matches:
        raise ValueError("component page contained no resolvable equity rows")

    exchange, mic = PRIMARY_MARKET_BY_COUNTRY[entry.country]
    refreshed_at = _utc_now()
    rows = []
    for stock in matches:
        symbol = str(stock["symbol"]).strip().upper()
        name = str(stock["name"] or stock["full_name"] or symbol).strip()
        rows.append({
            "symbol": symbol,
            "yahoo_symbol": resolve_yahoo_symbol(symbol, entry.country),
            "name": name,
            "full_name": str(stock["full_name"] or name).strip(),
            "country": entry.country,
            "market": entry.name,
            "exchange": exchange,
            "exchange_mic": mic,
            "isin": str(stock.get("isin") or "").strip(),
            "currency": str(stock.get("currency") or DEFAULT_CURRENCY_BY_COUNTRY[entry.country]).upper(),
            "source": "investing_index_component",
            "source_url": entry.components_url,
            "is_active": True,
            "refreshed_at": refreshed_at,
        })
    return pd.DataFrame(rows, columns=STOCK_UNIVERSE_COLUMNS)


def fetch_investing_index_catalog_universe(countries: Iterable[str]) -> pd.DataFrame:
    """Load companies from the requested Investing.com country/Europe index catalogs."""
    requested = set(countries)
    entries: list[InvestingIndexEntry] = []
    warnings: list[str] = []
    catalog_requests: list[tuple[str, set[str], str | None]] = []
    if "norway" in requested:
        entries.append(
            InvestingIndexEntry(
                name="OSE Benchmark (OSEBX)",
                country="norway",
                components_url=INVESTING_OSEBX_COMPONENTS_URL,
            )
        )
    for country in ("united states", "canada"):
        if country in requested:
            catalog_requests.append((INVESTING_INDEX_CATALOG_URLS[country], {country}, country))
    europe = requested & EUROPEAN_INDEX_COUNTRIES
    if europe:
        catalog_requests.append((INVESTING_INDEX_CATALOG_URLS["europe"], europe, None))

    for url, allowed, default_country in catalog_requests:
        try:
            discovered = _parse_investing_index_catalog(
                _download_text(url),
                allowed_countries=allowed,
                default_country=default_country,
            )
            if not discovered:
                raise ValueError("catalog contained no component-capable index links")
            entries.extend(discovered)
        except Exception as exc:
            warnings.append(f"Investing.com index catalog unavailable ({url}): {exc}")

    frames: list[pd.DataFrame] = []
    failed_components: list[str] = []
    if entries:
        try:
            stock_reference = _investpy_stock_reference()
        except Exception as exc:
            stock_reference = pd.DataFrame()
            warnings.append(f"Investing.com stock reference unavailable: {exc}")
        if not stock_reference.empty:
            # Catalogs contain many overlapping indexes. A small worker pool
            # keeps the daily universe refresh practical without flooding the
            # provider with one connection per index.
            with ThreadPoolExecutor(max_workers=min(6, len(entries))) as executor:
                futures = {
                    executor.submit(
                        _fetch_investing_index_components, entry, stock_reference
                    ): entry
                    for entry in entries
                }
                for future in as_completed(futures):
                    entry = futures[future]
                    try:
                        frames.append(future.result())
                    except Exception as exc:
                        failed_components.append(f"{entry.name}: {exc}")

    if failed_components:
        sample = "; ".join(failed_components[:5])
        suffix = f"; plus {len(failed_components) - 5} more" if len(failed_components) > 5 else ""
        warnings.append(f"Investing.com component pages skipped: {sample}{suffix}")
    result = (
        pd.concat(frames, ignore_index=True)[STOCK_UNIVERSE_COLUMNS]
        if frames else pd.DataFrame(columns=STOCK_UNIVERSE_COLUMNS)
    )
    result.attrs["warnings"] = warnings
    return result


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


def _constituent_csv(text: str, minimum_rows: int) -> tuple[pd.DataFrame, object, object | None]:
    lines = text.lstrip("\ufeff").splitlines()
    header_index = next((
        index for index, line in enumerate(lines)
        if len(line.replace('"', "").split(",")) >= 2
        and "ticker" in line.replace('"', "").split(",", 1)[0].strip().lower()
        and line.replace('"', "").split(",", 2)[1].strip().lower() == "name"
    ), None)
    if header_index is None:
        raise ValueError("No holdings CSV header with ticker and name was found.")
    frame = pd.read_csv(StringIO("\n".join(lines[header_index:])), dtype=str)
    asset_column = _find_column(frame, {"asset class"})
    if asset_column is not None:
        frame = frame[frame[asset_column].fillna("").str.lower() == "equity"]
    symbol_column = _find_column(frame, SYMBOL_COLUMN_NAMES)
    name_column = _find_column(frame, NAME_COLUMN_NAMES)
    if symbol_column is None or len(frame) < minimum_rows:
        raise ValueError(
            f"Holdings CSV contained {len(frame)} equity rows; expected at least {minimum_rows}."
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
    payload = _download_text(source.url)
    if source.format == "csv":
        frame, symbol_column, name_column = _constituent_csv(payload, source.minimum_rows)
    else:
        frame, symbol_column, name_column = _constituent_table(payload, source.minimum_rows)
    isin_column = _find_column(frame, ISIN_COLUMN_NAMES)
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
                "isin": (
                    str(row.get(isin_column, "")).strip()
                    if isin_column is not None
                    else ""
                ),
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
        sources = MAJOR_INDEXES_BY_COUNTRY[country]
    except KeyError as exc:
        raise ValueError(f"No major index is configured for {country!r}.") from exc
    frames: list[pd.DataFrame] = []
    warnings: list[str] = []
    for position, source in enumerate(sources):
        try:
            frames.append(_index_rows(source, country))
        except Exception as exc:
            if position == 0:
                raise
            warnings.append(f"{country} {source.name} enrichment skipped: {exc}")
    result = pd.concat(frames, ignore_index=True).drop_duplicates(
        ["country", "yahoo_symbol"], keep="first"
    )
    result.attrs["warnings"] = warnings
    return result


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
    requested_countries = list(countries)
    investing_catalog = fetch_investing_index_catalog_universe(requested_countries)
    warnings.extend(investing_catalog.attrs.get("warnings", []))
    for country in requested_countries:
        country_frames: list[pd.DataFrame] = []
        catalog_country = investing_catalog[investing_catalog["country"] == country]
        if not catalog_country.empty:
            country_frames.append(catalog_country)
        # Always retain the stable flagship mirror. It fills gaps when an
        # Investing.com component page is missing, blocked, or temporarily stale.
        stable_indexes = fetch_flagship_index_universe(country)
        warnings.extend(stable_indexes.attrs.get("warnings", []))
        country_frames.append(stable_indexes)
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
