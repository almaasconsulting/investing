from __future__ import annotations

import html
from typing import Any

import pandas as pd
import yfinance as yf


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


def _load_investpy() -> Any:
    try:
        import investpy
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Investing.com fundamentals require investpy and setuptools. "
            "Run: python -m pip install -r requirements.txt"
        ) from exc
    return investpy


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


def get_stock_fundamentals(symbol: str, country: str = "norway", source: str = "auto") -> dict[str, Any]:
    source = source.strip().lower()
    if source not in {"auto", "investing", "yahoo"}:
        raise ValueError("Fundamental data source must be one of: auto, investing, yahoo.")

    info = {}
    if source != "yahoo":
        try:
            investpy = _load_investpy()
            info = investpy.get_stock_information(stock=symbol, country=country, as_json=True)
        except Exception:
            pass

        fundamentals = {
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
        if any(fundamentals.values()):
            return fundamentals
        if source == "investing":
            return fundamentals

    yahoo_symbol = _resolve_yahoo_symbol(symbol, country)
    ticker = yf.Ticker(yahoo_symbol)
    info = ticker.info or {}
    return {
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
        "profit_margins": info.get("profitMargins"),
        "debt_to_equity": info.get("debtToEquity"),
        "current_ratio": info.get("currentRatio"),
        "free_cashflow": info.get("freeCashflow"),
    }


def format_fundamental_label(key: str) -> str:
    return html.escape(key.replace("_", " ").title())
