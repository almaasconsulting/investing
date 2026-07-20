from __future__ import annotations

import html
import math
from datetime import date
from typing import Any

import pandas as pd
import yfinance as yf

from investing.data_fetch.investpy_compat import load_investpy


def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else float("nan")


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("date").copy()
    df["ma20"] = df["close"].rolling(20, min_periods=1).mean()
    df["ma50"] = df["close"].rolling(50, min_periods=1).mean()
    df["ma200"] = df["close"].rolling(200, min_periods=1).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14, min_periods=14).mean()
    avg_loss = loss.rolling(14, min_periods=14).mean()
    rs = avg_gain / avg_loss
    df["rsi14"] = 100 - (100 / (1 + rs))

    def direction_value(row: pd.Series) -> str:
        if pd.notna(row["ma50"]) and pd.notna(row["ma200"]):
            if row["close"] > row["ma50"] > row["ma200"]:
                return "bullish"
            if row["close"] < row["ma50"] < row["ma200"]:
                return "bearish"
        if pd.notna(row["ma20"]) and pd.notna(row["ma50"]):
            if row["close"] > row["ma20"] > row["ma50"]:
                return "bullish"
            if row["close"] < row["ma20"] < row["ma50"]:
                return "bearish"
        return "neutral"

    def signal_summary(row: pd.Series) -> str:
        signals = []
        if pd.notna(row["ma20"]):
            signals.append("close above 20-day MA" if row["close"] > row["ma20"] else "close below 20-day MA")
        if pd.notna(row["ma50"]):
            signals.append("close above 50-day MA" if row["close"] > row["ma50"] else "close below 50-day MA")
        if pd.notna(row["ma200"]):
            signals.append("close above 200-day MA" if row["close"] > row["ma200"] else "close below 200-day MA")
        return ", ".join(signals)

    df["direction"] = df.apply(direction_value, axis=1)
    df["signal_summary"] = df.apply(signal_summary, axis=1)
    return df


def compute_technical_overview(df: pd.DataFrame) -> dict:
    df = add_technical_indicators(df)
    latest = df.sort_values("date").iloc[-1]
    close = float(latest["close"])
    return {
        "latest_close": close,
        "ma20": float(latest["ma20"]) if not pd.isna(latest["ma20"]) else None,
        "ma50": float(latest["ma50"]) if not pd.isna(latest["ma50"]) else None,
        "ma200": float(latest["ma200"]) if not pd.isna(latest["ma200"]) else None,
        "rsi": float(latest["rsi14"]) if not pd.isna(latest["rsi14"]) else None,
        "direction": latest["direction"],
        "signal_summary": latest["signal_summary"],
    }


def _lookup_fundamental(info: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in info and info[key] not in (None, "N/A", ""):
            return info[key]
    return None


def calculate_altman_z_score(
    *,
    total_assets: float,
    current_assets: float,
    current_liabilities: float,
    retained_earnings: float,
    ebit: float,
    market_value_equity: float,
    total_liabilities: float,
    revenue: float,
) -> float | None:
    """Calculate the original Altman Z-score for a public company.

    Returns ``None`` when a required input is missing/non-finite or when a
    denominator is not positive. The original model is primarily intended for
    publicly traded manufacturing companies.
    """
    values = (
        total_assets,
        current_assets,
        current_liabilities,
        retained_earnings,
        ebit,
        market_value_equity,
        total_liabilities,
        revenue,
    )
    try:
        numbers = [float(value) for value in values]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in numbers):
        return None
    (
        total_assets,
        current_assets,
        current_liabilities,
        retained_earnings,
        ebit,
        market_value_equity,
        total_liabilities,
        revenue,
    ) = numbers
    if total_assets <= 0 or total_liabilities <= 0:
        return None

    working_capital = current_assets - current_liabilities
    return (
        1.2 * working_capital / total_assets
        + 1.4 * retained_earnings / total_assets
        + 3.3 * ebit / total_assets
        + 0.6 * market_value_equity / total_liabilities
        + revenue / total_assets
    )


def altman_z_zone(score: float | None) -> str:
    """Classify an original Altman Z-score using its standard cutoffs."""
    if score is None:
        return "Unavailable"
    if score < 1.81:
        return "Distress"
    if score <= 2.99:
        return "Grey"
    return "Safe"


def _latest_statement_value(statement: pd.DataFrame, names: list[str]) -> float | None:
    if not isinstance(statement, pd.DataFrame) or statement.empty:
        return None
    normalized = {str(index).replace(" ", "").lower(): index for index in statement.index}
    for name in names:
        index = normalized.get(name.replace(" ", "").lower())
        if index is None:
            continue
        values = pd.to_numeric(statement.loc[index], errors="coerce").dropna()
        if not values.empty:
            return float(values.iloc[0])
    return None


def _get_altman_fundamentals(ticker: yf.Ticker, info: dict[str, Any]) -> dict[str, Any]:
    try:
        balance_sheet = ticker.balance_sheet
        income_statement = ticker.income_stmt
    except Exception:
        return {"altman_z_score": None, "altman_z_zone": "Unavailable"}

    inputs = {
        "total_assets": _latest_statement_value(balance_sheet, ["TotalAssets"]),
        "current_assets": _latest_statement_value(balance_sheet, ["CurrentAssets", "TotalCurrentAssets"]),
        "current_liabilities": _latest_statement_value(
            balance_sheet, ["CurrentLiabilities", "TotalCurrentLiabilities"]
        ),
        "retained_earnings": _latest_statement_value(balance_sheet, ["RetainedEarnings"]),
        "ebit": _latest_statement_value(income_statement, ["EBIT", "OperatingIncome"]),
        "market_value_equity": info.get("marketCap"),
        "total_liabilities": _latest_statement_value(
            balance_sheet,
            ["TotalLiabilitiesNetMinorityInterest", "TotalLiabilities"],
        ),
        "revenue": _latest_statement_value(income_statement, ["TotalRevenue", "OperatingRevenue"]),
    }
    score = calculate_altman_z_score(**inputs)
    return {
        "altman_z_score": round(score, 3) if score is not None else None,
        "altman_z_zone": altman_z_zone(score),
    }


def _load_investpy() -> Any:
    try:
        return load_investpy()
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Investing.com fundamentals require investpy and setuptools. "
            "Run: python -m pip install -r requirements.txt"
        ) from exc


def _parse_dividend_yield(value: Any) -> Any:
    try:
        if isinstance(value, str) and "%" in value:
            return value.split("(")[-1].strip().strip(")")
    except Exception:
        pass
    return value


def _resolve_yahoo_symbol(symbol: str, country: str = "norway") -> str:
    mapping = {
        "norway": ".OL",
        "canada": ".TO",
        "sweden": ".ST",
        "denmark": ".CO",
        "finland": ".HE",
        "switzerland": ".SW",
        "netherlands": ".AS",
        "spain": ".MC",
        "italy": ".MI",
        "germany": ".DE",
        "france": ".PA",
        "uk": ".L",
        "united kingdom": ".L",
    }
    symbol = symbol.strip()
    if "." in symbol:
        return symbol
    suffix = mapping.get(country.lower())
    return f"{symbol}{suffix}" if suffix else symbol


def _format_dividend_yield(value: Any) -> Any:
    try:
        if isinstance(value, (int, float)):
            if value > 1:
                if value <= 100:
                    return f"{value:.2f}%"
                return f"{value / 100:.2f}%"
            return f"{value * 100:.2f}%"
        if isinstance(value, str) and value.strip():
            return value
    except Exception:
        pass
    return value


def _format_change(value: Any) -> Any:
    try:
        if isinstance(value, (int, float)):
            return f"{value * 100:.2f}%"
    except Exception:
        pass
    return value


def _ratio(numerator: Any, denominator: Any) -> float | None:
    try:
        numerator = float(numerator)
        denominator = float(denominator)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numerator) or not math.isfinite(denominator) or denominator <= 0:
        return None
    return numerator / denominator


def _has_value(value: Any) -> bool:
    if value is None or value == "" or value == "N/A":
        return False
    try:
        return not bool(pd.isna(value))
    except (TypeError, ValueError):
        return True


def merge_fundamentals(
    yahoo: dict[str, Any],
    investing: dict[str, Any],
) -> dict[str, Any]:
    """Merge provider fundamentals field-by-field with Yahoo precedence."""
    merged: dict[str, Any] = {}
    field_sources: dict[str, str] = {}
    for key in dict.fromkeys([*yahoo, *investing]):
        if _has_value(yahoo.get(key)):
            merged[key] = yahoo[key]
            field_sources[key] = "yahoo"
        elif _has_value(investing.get(key)):
            merged[key] = investing[key]
            field_sources[key] = "investing"
        else:
            merged[key] = None

    providers_used = [
        provider
        for provider in ("yahoo", "investing")
        if provider in field_sources.values()
    ]
    merged["field_sources"] = field_sources
    merged["providers_used"] = providers_used
    merged["provider_payloads"] = {"yahoo": yahoo, "investing": investing}
    return merged


def compute_dividend_history_metrics(dividends: Any) -> dict[str, Any]:
    """Summarize annual dividend payments from a Series or provider DataFrame."""
    if isinstance(dividends, pd.Series):
        frame = pd.DataFrame({"date": dividends.index, "amount": dividends.values})
    elif isinstance(dividends, pd.DataFrame) and not dividends.empty:
        date_column = next(
            (column for column in dividends.columns if str(column).lower() in {"date", "payment date"}),
            None,
        )
        amount_column = next(
            (column for column in dividends.columns if str(column).lower() in {"dividend", "amount"}),
            None,
        )
        if date_column is None:
            frame = dividends.reset_index()
            date_column = frame.columns[0]
        else:
            frame = dividends.copy()
        if amount_column is None:
            candidates = [column for column in frame.columns if column != date_column]
            amount_column = candidates[0] if candidates else None
        if amount_column is None:
            return {}
        frame = frame[[date_column, amount_column]].rename(
            columns={date_column: "date", amount_column: "amount"}
        )
    elif dividends is not None:
        return {
            "dividend_years_paid": 0,
            "consecutive_dividend_years": 0,
            "dividend_cagr_5y": None,
        }
    else:
        return {}

    if frame.empty:
        return {
            "dividend_years_paid": 0,
            "consecutive_dividend_years": 0,
            "dividend_cagr_5y": None,
        }

    # Provider dividend indexes can contain timezone-aware values from several
    # exchanges.  Normalizing through UTC avoids pandas rejecting a mixed set
    # of timezone-aware datetime objects.
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce", utc=True).dt.tz_convert(None)
    frame["amount"] = pd.to_numeric(
        frame["amount"].astype(str).str.replace(r"[^0-9.\-]", "", regex=True),
        errors="coerce",
    )
    frame = frame.dropna(subset=["date", "amount"])
    frame = frame[frame["amount"] > 0]
    if frame.empty:
        return {
            "dividend_years_paid": 0,
            "consecutive_dividend_years": 0,
            "dividend_cagr_5y": None,
        }

    annual = frame.groupby(frame["date"].dt.year)["amount"].sum().sort_index()
    latest_year = int(annual.index.max())
    current_year = date.today().year
    consecutive_years = 0
    if latest_year >= current_year - 1:
        year = latest_year
        while year in annual.index and annual.loc[year] > 0:
            consecutive_years += 1
            year -= 1

    completed = annual[annual.index < current_year]
    recent = completed.tail(6)
    dividend_cagr = None
    if len(recent) >= 2:
        year_span = int(recent.index[-1] - recent.index[0])
        if year_span > 0 and recent.iloc[0] > 0 and recent.iloc[-1] > 0:
            dividend_cagr = float((recent.iloc[-1] / recent.iloc[0]) ** (1 / year_span) - 1)

    return {
        "dividend_years_paid": int(len(annual)),
        "consecutive_dividend_years": consecutive_years,
        "dividend_cagr_5y": dividend_cagr,
        "latest_dividend_year": latest_year,
    }


def _get_yahoo_dividend_metrics(ticker: yf.Ticker) -> dict[str, Any]:
    # Some Yahoo instruments reject the implicit ``period="max"`` used by
    # ``Ticker.dividends`` and only advertise very short periods. Try the
    # richest history first, then degrade without failing the stock batch.
    for period in ("max", "5d", "1d"):
        try:
            history = ticker.history(
                period=period,
                interval="1d",
                actions=True,
                auto_adjust=False,
                # Let the fallback loop handle unsupported periods. Without
                # this, yfinance logs an ERROR before returning an empty frame.
                raise_errors=True,
            )
        except Exception:
            continue
        if history is None or history.empty:
            continue
        dividends = history.get("Dividends")
        if dividends is None:
            return compute_dividend_history_metrics(pd.Series(dtype=float))
        return compute_dividend_history_metrics(dividends)
    return {}


def _get_investing_dividend_metrics(investpy: Any, symbol: str, country: str) -> dict[str, Any]:
    try:
        dividends = investpy.get_stock_dividends(stock=symbol, country=country)
        return compute_dividend_history_metrics(dividends)
    except Exception:
        return {}


def get_stock_fundamentals(
    symbol: str,
    country: str = "norway",
    source: str = "auto",
    yahoo_symbol: str = "",
) -> dict[str, Any]:
    source = source.strip().lower()
    if source not in {"auto", "investing", "yahoo"}:
        raise ValueError("Fundamental data source must be one of: auto, investing, yahoo.")

    info = {}
    investing_fundamentals: dict[str, Any] = {}
    if source != "yahoo":
        investpy = None
        try:
            investpy = _load_investpy()
            info = investpy.get_stock_information(stock=symbol, country=country, as_json=True)
        except Exception:
            pass

        investing_fundamentals = {
            "market_cap": _lookup_fundamental(info, ["Market Cap", "Market Capitalization"]),
            "pe_ratio": _lookup_fundamental(info, ["P/E Ratio", "PE Ratio"]),
            "eps": _lookup_fundamental(info, ["EPS"]),
            "dividend_yield": _parse_dividend_yield(_lookup_fundamental(info, ["Dividend (Yield)"])),
            "beta": _lookup_fundamental(info, ["Beta"]),
            "one_year_change": _lookup_fundamental(info, ["1-Year Change", "1 Year Change"]),
            "shares_outstanding": _lookup_fundamental(info, ["Shares Outstanding"]),
            "revenue": _lookup_fundamental(info, ["Revenue"]),
            "prev_close": _lookup_fundamental(info, ["Prev. Close"]),
        }
        if investpy is not None:
            investing_fundamentals.update(
                _get_investing_dividend_metrics(investpy, symbol, country)
            )
        if source == "investing":
            return merge_fundamentals({}, investing_fundamentals)

    yahoo_symbol = yahoo_symbol.strip() or _resolve_yahoo_symbol(symbol, country)
    try:
        ticker = yf.Ticker(yahoo_symbol)
        info = ticker.info or {}
    except Exception:
        if any(investing_fundamentals.values()):
            return merge_fundamentals({}, investing_fundamentals)
        raise
    yahoo_fundamentals = {
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
        "eps": info.get("trailingEps") or info.get("forwardEps"),
        "dividend_yield": _format_dividend_yield(info.get("dividendYield")),
        "beta": info.get("beta"),
        "one_year_change": _format_change(info.get("fiftyTwoWeekChange")),
        "shares_outstanding": info.get("sharesOutstanding"),
        "revenue": info.get("totalRevenue") or info.get("revenue"),
        "prev_close": info.get("previousClose"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "revenue_growth": info.get("revenueGrowth"),
        "earnings_growth": info.get("earningsGrowth"),
        "return_on_equity": info.get("returnOnEquity"),
        "return_on_assets": info.get("returnOnAssets"),
        "profit_margins": info.get("profitMargins"),
        "operating_margins": info.get("operatingMargins"),
        "gross_margins": info.get("grossMargins"),
        "debt_to_equity": info.get("debtToEquity"),
        "current_ratio": info.get("currentRatio"),
        "free_cashflow": info.get("freeCashflow"),
        "free_cashflow_yield": _ratio(info.get("freeCashflow"), info.get("marketCap")),
        "price_to_book": info.get("priceToBook"),
        "enterprise_to_ebitda": info.get("enterpriseToEbitda"),
        "peg_ratio": info.get("pegRatio") or info.get("trailingPegRatio"),
        "payout_ratio": info.get("payoutRatio"),
        "funds_from_operations": info.get("fundsFromOperations"),
        "funds_from_operations_yield": _ratio(info.get("fundsFromOperations"), info.get("marketCap")),
        **_get_yahoo_dividend_metrics(ticker),
        **_get_altman_fundamentals(ticker, info),
    }
    if source == "yahoo":
        return merge_fundamentals(yahoo_fundamentals, {})
    return merge_fundamentals(yahoo_fundamentals, investing_fundamentals)


def format_fundamental_label(key: str) -> str:
    return html.escape(key.replace("_", " ").title())
