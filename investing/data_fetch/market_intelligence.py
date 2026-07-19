from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import yfinance as yf

from investing.data_fetch.investing_com import resolve_yahoo_symbol
from investing.data_fetch.investpy_compat import load_investpy


STATEMENT_TYPES = {
    "income_statement": "income",
    "balance_sheet": "balance_sheet",
    "cash_flow_statement": "cash_flow",
}

LINE_ITEM_ALIASES = {
    "total_revenue": "revenue",
    "operating_revenue": "revenue",
    "gross_profit": "gross_profit",
    "operating_income": "operating_income",
    "ebit": "operating_income",
    "ebitda": "ebitda",
    "net_income": "net_income",
    "net_income_common_stockholders": "net_income",
    "diluted_eps": "diluted_eps",
    "basic_eps": "basic_eps",
    "total_assets": "total_assets",
    "total_liabilities_net_minority_interest": "total_liabilities",
    "total_liabilities": "total_liabilities",
    "stockholders_equity": "stockholders_equity",
    "total_equity_gross_minority_interest": "stockholders_equity",
    "cash_cash_equivalents_and_short_term_investments": "cash_and_equivalents",
    "cash_and_short_term_investments": "cash_and_equivalents",
    "cash_and_cash_equivalents": "cash_and_equivalents",
    "total_debt": "total_debt",
    "operating_cash_flow": "operating_cash_flow",
    "cash_from_operating_activities": "operating_cash_flow",
    "capital_expenditure": "capital_expenditure",
    "capital_expenditures": "capital_expenditure",
    "free_cash_flow": "free_cash_flow",
    "common_stock_dividend_paid": "dividends_paid",
    "cash_dividends_paid": "dividends_paid",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _snake_case(value: Any) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value).strip())
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()


def canonical_line_item(value: Any) -> str:
    normalized = _snake_case(value)
    return LINE_ITEM_ALIASES.get(normalized, normalized)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "--", "N/A", "nan", "None"}:
        return None
    multiplier = 1.0
    if text[-1:].upper() in {"K", "M", "B", "T"}:
        multiplier = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[text[-1].upper()]
        text = text[:-1]
    try:
        return float(text.replace("%", "")) * multiplier
    except ValueError:
        return None


def _investing_statement_value(raw_line_item: Any, value: Any) -> float | None:
    """Convert Investing.com summary amounts from displayed millions to base units."""
    number = _number(value)
    if number is None:
        return None
    line_item = canonical_line_item(raw_line_item)
    if any(token in line_item for token in ("eps", "per_share", "ratio", "margin", "percent")):
        return number
    return number * 1_000_000.0


def _statement_row(
    *,
    symbol: str,
    country: str,
    provider: str,
    statement_type: str,
    period_type: str,
    period_end: Any,
    raw_line_item: Any,
    value: Any,
    currency: str = "",
) -> dict[str, Any] | None:
    period = pd.to_datetime(period_end, errors="coerce")
    numeric_value = _number(value)
    if pd.isna(period) or numeric_value is None:
        return None
    raw_name = str(raw_line_item).strip()
    canonical = canonical_line_item(raw_name)
    natural_key = "|".join(
        [country.lower(), symbol.upper(), provider, statement_type, period_type,
         period.date().isoformat(), canonical, currency.upper()]
    )
    record_hash = hashlib.sha256(f"{natural_key}|{numeric_value}".encode("utf-8")).hexdigest()
    return {
        "statement_key": hashlib.sha256(natural_key.encode("utf-8")).hexdigest(),
        "record_hash": record_hash,
        "ticker": symbol.upper(),
        "yahoo_symbol": resolve_yahoo_symbol(symbol, country),
        "country": country.lower(),
        "provider": provider,
        "statement_type": statement_type,
        "period_type": period_type,
        "fiscal_period_end": period.date(),
        "raw_line_item": raw_name,
        "canonical_line_item": canonical,
        "line_item": canonical,
        "line_item_label": raw_name,
        "value": numeric_value,
        "currency": currency.upper(),
        "reported_at": None,
        "fetched_at": _utc_now(),
        "raw_payload_json": "",
    }


def _yahoo_statement_rows(
    symbol: str, country: str, yahoo_symbol: str = "", currency: str = ""
) -> list[dict[str, Any]]:
    ticker = yf.Ticker(yahoo_symbol or resolve_yahoo_symbol(symbol, country))
    try:
        currency = str(ticker.fast_info.get("currency") or currency or "")
    except Exception:
        pass
    getters = {
        "income": ticker.get_income_stmt,
        "balance_sheet": ticker.get_balance_sheet,
        "cash_flow": ticker.get_cash_flow,
    }
    rows: list[dict[str, Any]] = []
    for period_type, frequency in (("annual", "yearly"), ("quarterly", "quarterly")):
        for statement_type, getter in getters.items():
            try:
                frame = getter(freq=frequency, pretty=False)
            except Exception:
                continue
            if not isinstance(frame, pd.DataFrame) or frame.empty:
                continue
            for period_end in frame.columns:
                for raw_line_item, value in frame[period_end].items():
                    row = _statement_row(
                        symbol=symbol,
                        country=country,
                        provider="yahoo",
                        statement_type=statement_type,
                        period_type=period_type,
                        period_end=period_end,
                        raw_line_item=raw_line_item,
                        value=value,
                        currency=currency,
                    )
                    if row:
                        row["raw_payload_json"] = frame.to_json(date_format="iso")
                        rows.append(row)
    return rows


def _investing_statement_rows(
    symbol: str, country: str, currency: str = ""
) -> list[dict[str, Any]]:
    investpy = load_investpy()

    rows: list[dict[str, Any]] = []
    for period_type in ("annual", "quarterly"):
        for investing_type, statement_type in STATEMENT_TYPES.items():
            try:
                frame = investpy.get_stock_financial_summary(
                    stock=symbol,
                    country=country,
                    summary_type=investing_type,
                    period=period_type,
                )
            except Exception:
                continue
            if not isinstance(frame, pd.DataFrame) or frame.empty:
                continue
            for period_end, values in frame.iterrows():
                for raw_line_item, value in values.items():
                    row = _statement_row(
                        symbol=symbol,
                        country=country,
                        provider="investing",
                        statement_type=statement_type,
                        period_type=period_type,
                        period_end=period_end,
                        raw_line_item=raw_line_item,
                        value=_investing_statement_value(raw_line_item, value),
                        currency=currency,
                    )
                    if row:
                        row["raw_payload_json"] = frame.to_json(date_format="iso")
                        rows.append(row)
    return rows


def fetch_financial_statements(
    symbol: str,
    country: str = "norway",
    *,
    yahoo_symbol: str = "",
    currency: str = "",
    source: str = "auto",
) -> pd.DataFrame:
    """Fetch long-form statements, retaining both providers in auto mode."""
    source = source.strip().lower()
    if source not in {"auto", "yahoo", "investing"}:
        raise ValueError("Statement source must be auto, yahoo, or investing.")
    rows: list[dict[str, Any]] = []
    if source in {"auto", "yahoo"}:
        rows.extend(_yahoo_statement_rows(symbol, country, yahoo_symbol, currency))
    if source in {"auto", "investing"}:
        rows.extend(_investing_statement_rows(symbol, country, currency))
    return pd.DataFrame(rows)


def _nested_url(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("url") or "")
    return ""


def _published_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime().replace(tzinfo=None)


def fetch_stock_news(
    symbol: str,
    country: str = "norway",
    *,
    yahoo_symbol: str = "",
    count: int = 25,
) -> pd.DataFrame:
    """Fetch Yahoo news metadata for a stock without downloading article bodies."""
    yahoo_symbol = yahoo_symbol or resolve_yahoo_symbol(symbol, country)
    items = yf.Ticker(yahoo_symbol).get_news(count=count, tab="all") or []
    fetched_at = _utc_now()
    rows: list[dict[str, Any]] = []
    for item in items:
        content = item.get("content", item) if isinstance(item, dict) else {}
        if not isinstance(content, dict):
            continue
        title = str(content.get("title") or "").strip()
        url = (
            _nested_url(content.get("canonicalUrl"))
            or _nested_url(content.get("clickThroughUrl"))
            or str(content.get("link") or "")
        ).strip()
        published_at = _published_at(
            content.get("pubDate") or content.get("providerPublishTime")
        )
        provider = content.get("provider") or {}
        publisher = (
            provider.get("displayName") if isinstance(provider, dict) else provider
        ) or content.get("publisher") or "Yahoo Finance"
        external_id = str(content.get("id") or item.get("uuid") or "")
        identity = url.lower() or f"{external_id}|{title.lower()}|{published_at}"
        if not title and not url:
            continue
        rows.append(
            {
                "article_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                "ticker": symbol.upper(),
                "yahoo_symbol": yahoo_symbol,
                "country": country.lower(),
                "provider": "yahoo",
                "provider_article_id": external_id,
                "published_at": published_at,
                "title": title,
                "publisher": str(publisher),
                "summary": str(content.get("summary") or content.get("description") or ""),
                "url": url,
                "content_type": str(content.get("contentType") or "news"),
                "thumbnail_url": _nested_url(content.get("thumbnail")),
                "raw_payload_json": json.dumps(item, default=str, sort_keys=True),
                "fetched_at": fetched_at,
                "record_hash": hashlib.sha256(
                    f"{identity}|{json.dumps(item, default=str, sort_keys=True)}".encode("utf-8")
                ).hexdigest(),
            }
        )
    return pd.DataFrame(rows)
