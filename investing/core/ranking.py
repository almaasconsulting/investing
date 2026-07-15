from __future__ import annotations

import math
from typing import Any

import pandas as pd


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, str) and value.strip() in {"", "N/A", "nan"}:
        return None
    if isinstance(value, (int, float)):
        if math.isnan(value):
            return None
        return float(value)

    text = str(value).strip().replace(",", "")
    if not text:
        return None

    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1].strip()

    multiplier = 1.0
    suffix = text[-1:].upper()
    if suffix in {"K", "M", "B", "T"}:
        text = text[:-1]
        multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}[suffix]

    try:
        number = float(text) * multiplier
    except ValueError:
        return None

    return number / 100 if is_percent else number


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def score_positive(value: float | None, good: float, excellent: float) -> float:
    if value is None:
        return 50.0
    if excellent == good:
        return 50.0
    return clamp((value - good) / (excellent - good) * 100)


def score_lower_better(value: float | None, good: float, bad: float) -> float:
    if value is None:
        return 50.0
    if bad == good:
        return 50.0
    return clamp((bad - value) / (bad - good) * 100)


def score_pe(value: float | None) -> float:
    if value is None or value <= 0:
        return 45.0
    if 8 <= value <= 18:
        return 100.0
    if 0 < value < 8:
        return clamp(70 + value / 8 * 30)
    return score_lower_better(value, good=18, bad=45)


def score_rsi(value: float | None) -> float:
    if value is None:
        return 50.0
    if 45 <= value <= 65:
        return 100.0
    if value < 45:
        return clamp(100 - (45 - value) * 2.5)
    return clamp(100 - (value - 65) * 3.0)


def score_direction(value: str | None) -> float:
    if value == "bullish":
        return 100.0
    if value == "neutral":
        return 60.0
    if value == "bearish":
        return 15.0
    return 50.0


def dividend_bucket(value: Any) -> str:
    dividend = parse_number(value)
    if dividend is None or dividend <= 0:
        return "No/unknown dividend"
    if dividend < 0.02:
        return "Low yield"
    if dividend < 0.05:
        return "Medium yield"
    return "High yield"


def valuation_bucket(value: Any) -> str:
    pe = parse_number(value)
    if pe is None or pe <= 0:
        return "No/unknown P/E"
    if pe < 10:
        return "Low P/E"
    if pe <= 25:
        return "Moderate P/E"
    return "High P/E"


def _result_row(result: dict) -> dict:
    scorecard = result.get("scorecard", {})
    technical = result.get("technical", {})
    fundamentals = result.get("fundamentals", {})

    score = parse_number(scorecard.get("score"))
    price_change = parse_number(scorecard.get("price_change"))
    volatility = parse_number(scorecard.get("volatility"))
    rsi = parse_number(technical.get("rsi"))
    pe = parse_number(fundamentals.get("pe_ratio"))
    eps = parse_number(fundamentals.get("eps"))
    dividend = parse_number(fundamentals.get("dividend_yield"))
    beta = parse_number(fundamentals.get("beta"))
    revenue_growth = parse_number(fundamentals.get("revenue_growth"))
    earnings_growth = parse_number(fundamentals.get("earnings_growth"))
    return_on_equity = parse_number(fundamentals.get("return_on_equity"))
    debt_to_equity = parse_number(fundamentals.get("debt_to_equity"))
    profit_margins = parse_number(fundamentals.get("profit_margins"))

    technical_score = (
        score_positive(score, good=-0.01, excellent=0.04) * 0.30
        + score_positive(price_change, good=-0.10, excellent=0.35) * 0.20
        + score_lower_better(volatility, good=0.015, bad=0.08) * 0.20
        + score_rsi(rsi) * 0.15
        + score_direction(technical.get("direction")) * 0.15
    )

    fundamental_score = (
        score_pe(pe) * 0.24
        + score_positive(eps, good=0, excellent=20) * 0.12
        + score_positive(dividend, good=0, excellent=0.06) * 0.12
        + score_lower_better(beta, good=0.7, bad=1.8) * 0.10
        + score_positive(revenue_growth, good=-0.05, excellent=0.25) * 0.10
        + score_positive(earnings_growth, good=-0.05, excellent=0.25) * 0.10
        + score_positive(return_on_equity, good=0, excellent=0.20) * 0.10
        + score_lower_better(debt_to_equity, good=40, bad=200) * 0.06
        + score_positive(profit_margins, good=0, excellent=0.20) * 0.06
    )

    return {
        "symbol": result.get("symbol"),
        "yahoo_symbol": result.get("yahoo_symbol"),
        "name": result.get("name"),
        "country": result.get("country"),
        "market": result.get("universe_market") or result.get("exchange"),
        "exchange": result.get("exchange"),
        "sector": fundamentals.get("sector") or "Unknown",
        "industry": fundamentals.get("industry") or "Unknown",
        "direction": technical.get("direction") or "unknown",
        "recommended": scorecard.get("recommended"),
        "technical_score": round(technical_score, 3),
        "fundamental_score": round(fundamental_score, 3),
        "score": score,
        "price_change": price_change,
        "volatility": volatility,
        "rsi": rsi,
        "pe_ratio": pe,
        "eps": eps,
        "dividend_yield": dividend,
        "beta": beta,
        "revenue_growth": revenue_growth,
        "earnings_growth": earnings_growth,
        "return_on_equity": return_on_equity,
        "debt_to_equity": debt_to_equity,
        "profit_margins": profit_margins,
        "valuation_bucket": valuation_bucket(pe),
        "dividend_bucket": dividend_bucket(dividend),
    }


def build_rankings(
    results: list[dict],
    technical_weight: float = 0.55,
    group_by: str = "correlation_cluster",
    cluster_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    rows = [_result_row(result) for result in results if not result.get("error")]
    if not rows:
        return pd.DataFrame()

    technical_weight = clamp(technical_weight, 0.0, 1.0)
    fundamental_weight = 1.0 - technical_weight
    frame = pd.DataFrame(rows)
    frame["ranking_score"] = (
        frame["technical_score"] * technical_weight
        + frame["fundamental_score"] * fundamental_weight
    ).round(3)

    grouping_column = {
        "correlation_cluster": "correlation_cluster",
        "market": "market",
        "country": "country",
        "sector": "sector",
        "industry": "industry",
        "technical_direction": "direction",
        "recommendation": "recommended",
        "valuation": "valuation_bucket",
        "dividend": "dividend_bucket",
        "none": "group",
    }.get(group_by, "correlation_cluster")

    if grouping_column == "correlation_cluster":
        cluster_map = cluster_map or {}
        frame["correlation_cluster"] = frame["symbol"].map(cluster_map).fillna("Unclustered")
    elif grouping_column == "group":
        frame["group"] = "All selected stocks"

    frame["group"] = frame[grouping_column].astype(str)
    frame = frame.sort_values(["group", "ranking_score"], ascending=[True, False])
    frame["group_rank"] = frame.groupby("group").cumcount() + 1
    return frame
