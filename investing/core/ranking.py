from __future__ import annotations

import math
from typing import Any

import pandas as pd

RANKING_API_VERSION = 2


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


SECTOR_ALIASES = {
    "materials": "Basic Materials",
    "basic materials": "Basic Materials",
    "communication services": "Communication Services",
    "consumer discretionary": "Consumer Cyclical",
    "consumer cyclical": "Consumer Cyclical",
    "consumer staples": "Consumer Defensive",
    "consumer defensive": "Consumer Defensive",
    "energy": "Energy",
    "financials": "Financial Services",
    "financial services": "Financial Services",
    "health care": "Healthcare",
    "healthcare": "Healthcare",
    "industrials": "Industrials",
    "information technology": "Technology",
    "technology": "Technology",
    "real estate": "Real Estate",
    "utilities": "Utilities",
}

METRIC_LABELS = {
    "pe_ratio": "P/E",
    "price_to_book": "Price/book",
    "enterprise_to_ebitda": "EV/EBITDA",
    "peg_ratio": "PEG",
    "free_cashflow_yield": "Free-cash-flow yield",
    "funds_from_operations_yield": "FFO yield",
    "dividend_yield": "Dividend yield",
    "dividend_quality": "Dividend quality/history",
    "consecutive_dividend_years": "Consecutive dividend years",
    "dividend_cagr_5y": "5-year dividend growth",
    "payout_ratio": "Payout sustainability",
    "revenue_growth": "Revenue growth",
    "earnings_growth": "Earnings growth",
    "return_on_equity": "Return on equity",
    "return_on_assets": "Return on assets",
    "operating_margins": "Operating margin",
    "profit_margins": "Net margin",
    "debt_to_equity": "Debt/equity",
    "altman_z_score": "Altman Z-score",
    "beta": "Beta",
}

# Weights express which reported fundamentals are most decision-useful for each
# sector. They are intentionally transparent heuristics, not fitted predictions.
SECTOR_FUNDAMENTAL_PROFILES: dict[str, dict[str, float]] = {
    "Basic Materials": {
        "pe_ratio": 0.10,
        "enterprise_to_ebitda": 0.15,
        "free_cashflow_yield": 0.15,
        "debt_to_equity": 0.15,
        "altman_z_score": 0.10,
        "return_on_equity": 0.10,
        "operating_margins": 0.10,
        "revenue_growth": 0.10,
        "earnings_growth": 0.05,
    },
    "Communication Services": {
        "pe_ratio": 0.10,
        "enterprise_to_ebitda": 0.15,
        "free_cashflow_yield": 0.15,
        "revenue_growth": 0.15,
        "earnings_growth": 0.10,
        "operating_margins": 0.15,
        "debt_to_equity": 0.10,
        "return_on_equity": 0.10,
    },
    "Consumer Cyclical": {
        "pe_ratio": 0.15,
        "enterprise_to_ebitda": 0.10,
        "free_cashflow_yield": 0.10,
        "revenue_growth": 0.10,
        "earnings_growth": 0.15,
        "operating_margins": 0.15,
        "return_on_equity": 0.10,
        "debt_to_equity": 0.10,
        "beta": 0.05,
    },
    "Consumer Defensive": {
        "pe_ratio": 0.15,
        "free_cashflow_yield": 0.15,
        "dividend_yield": 0.15,
        "payout_ratio": 0.10,
        "revenue_growth": 0.05,
        "earnings_growth": 0.05,
        "operating_margins": 0.15,
        "return_on_equity": 0.10,
        "debt_to_equity": 0.10,
    },
    "Energy": {
        "pe_ratio": 0.05,
        "enterprise_to_ebitda": 0.20,
        "free_cashflow_yield": 0.20,
        "debt_to_equity": 0.15,
        "dividend_yield": 0.15,
        "return_on_equity": 0.10,
        "operating_margins": 0.10,
        "revenue_growth": 0.05,
    },
    "Financial Services": {
        "pe_ratio": 0.15,
        "price_to_book": 0.20,
        "return_on_equity": 0.25,
        "return_on_assets": 0.20,
        "earnings_growth": 0.10,
        "dividend_yield": 0.05,
        "payout_ratio": 0.05,
    },
    "Healthcare": {
        "pe_ratio": 0.10,
        "enterprise_to_ebitda": 0.10,
        "free_cashflow_yield": 0.15,
        "revenue_growth": 0.20,
        "earnings_growth": 0.20,
        "operating_margins": 0.15,
        "return_on_equity": 0.05,
        "debt_to_equity": 0.05,
    },
    "Industrials": {
        "pe_ratio": 0.10,
        "enterprise_to_ebitda": 0.10,
        "free_cashflow_yield": 0.15,
        "debt_to_equity": 0.15,
        "altman_z_score": 0.10,
        "return_on_equity": 0.15,
        "operating_margins": 0.10,
        "revenue_growth": 0.05,
        "earnings_growth": 0.10,
    },
    "Real Estate": {
        "funds_from_operations_yield": 0.25,
        "dividend_yield": 0.20,
        "enterprise_to_ebitda": 0.15,
        "debt_to_equity": 0.15,
        "revenue_growth": 0.10,
        "free_cashflow_yield": 0.10,
        "beta": 0.05,
    },
    "Technology": {
        "peg_ratio": 0.10,
        "enterprise_to_ebitda": 0.10,
        "free_cashflow_yield": 0.15,
        "revenue_growth": 0.20,
        "earnings_growth": 0.15,
        "operating_margins": 0.15,
        "return_on_equity": 0.10,
        "debt_to_equity": 0.05,
    },
    "Utilities": {
        "pe_ratio": 0.10,
        "enterprise_to_ebitda": 0.15,
        "dividend_yield": 0.20,
        "payout_ratio": 0.10,
        "debt_to_equity": 0.15,
        "return_on_equity": 0.10,
        "earnings_growth": 0.05,
        "free_cashflow_yield": 0.10,
        "beta": 0.05,
    },
    "Diversified": {
        "pe_ratio": 0.15,
        "enterprise_to_ebitda": 0.10,
        "free_cashflow_yield": 0.15,
        "revenue_growth": 0.10,
        "earnings_growth": 0.10,
        "return_on_equity": 0.15,
        "operating_margins": 0.10,
        "debt_to_equity": 0.10,
        "altman_z_score": 0.05,
    },
}

SECTOR_DIVIDEND_WEIGHTS = {
    "Basic Materials": 0.10,
    "Communication Services": 0.08,
    "Consumer Cyclical": 0.08,
    "Consumer Defensive": 0.15,
    "Energy": 0.15,
    "Financial Services": 0.12,
    "Healthcare": 0.05,
    "Industrials": 0.10,
    "Real Estate": 0.20,
    "Technology": 0.05,
    "Utilities": 0.20,
    "Diversified": 0.10,
}

# A yield is judged against the economics of its sector. The first value is
# where a yield becomes strong; the second is the upper end of the ideal band.
SECTOR_DIVIDEND_YIELD_BANDS = {
    "Basic Materials": (0.025, 0.055),
    "Communication Services": (0.018, 0.045),
    "Consumer Cyclical": (0.018, 0.045),
    "Consumer Defensive": (0.025, 0.055),
    "Energy": (0.030, 0.065),
    "Financial Services": (0.025, 0.060),
    "Healthcare": (0.015, 0.035),
    "Industrials": (0.020, 0.050),
    "Real Estate": (0.035, 0.075),
    "Technology": (0.010, 0.030),
    "Utilities": (0.030, 0.065),
    "Diversified": (0.020, 0.050),
}


def normalize_sector(value: Any) -> str:
    text = str(value or "").strip()
    return SECTOR_ALIASES.get(text.lower(), "Diversified")


def _score_sustainable_payout(value: float | None) -> float:
    if value is None:
        return 50.0
    if value < 0 or value > 1.25:
        return 0.0
    if 0.20 <= value <= 0.70:
        return 100.0
    if value < 0.20:
        return clamp(value / 0.20 * 100)
    return clamp((1.25 - value) / (1.25 - 0.70) * 100)


def _score_sector_dividend_yield(value: float | None, sector: str) -> float:
    if value is None:
        return 50.0
    if value <= 0:
        return 0.0
    strong, ideal_high = SECTOR_DIVIDEND_YIELD_BANDS[sector]
    if value < strong:
        return clamp(value / strong * 100)
    if value <= ideal_high:
        return 100.0
    excessive = ideal_high * 2
    return clamp(100 - (value - ideal_high) / (excessive - ideal_high) * 80, 20, 100)


def build_dividend_quality_score(fundamentals: dict[str, Any], sector: str) -> dict[str, Any]:
    values = {
        "dividend_yield": parse_number(fundamentals.get("dividend_yield")),
        "consecutive_dividend_years": parse_number(fundamentals.get("consecutive_dividend_years")),
        "dividend_cagr_5y": parse_number(fundamentals.get("dividend_cagr_5y")),
        "payout_ratio": parse_number(fundamentals.get("payout_ratio")),
    }
    weights = {
        "dividend_yield": 0.35,
        "consecutive_dividend_years": 0.35,
        "dividend_cagr_5y": 0.20,
        "payout_ratio": 0.10,
    }
    scores = {
        "dividend_yield": _score_sector_dividend_yield(values["dividend_yield"], sector),
        "consecutive_dividend_years": score_positive(
            values["consecutive_dividend_years"], good=0, excellent=10
        ),
        "dividend_cagr_5y": score_positive(values["dividend_cagr_5y"], good=-0.05, excellent=0.10),
        "payout_ratio": _score_sustainable_payout(values["payout_ratio"]),
    }
    score = sum(scores[metric] * weight for metric, weight in weights.items())
    coverage = sum(weight for metric, weight in weights.items() if values[metric] is not None)
    return {
        "score": round(score, 3),
        "coverage": coverage,
        "component_scores": {metric: round(value, 3) for metric, value in scores.items()},
    }


def score_fundamental_metric(metric: str, value: float | None, sector: str = "Diversified") -> float:
    if metric == "pe_ratio":
        return score_pe(value)
    if metric == "price_to_book":
        return 20.0 if value is not None and value <= 0 else score_lower_better(value, good=1.5, bad=6.0)
    if metric == "enterprise_to_ebitda":
        return 20.0 if value is not None and value <= 0 else score_lower_better(value, good=8.0, bad=25.0)
    if metric == "peg_ratio":
        return 20.0 if value is not None and value <= 0 else score_lower_better(value, good=1.0, bad=3.0)
    if metric == "free_cashflow_yield":
        return score_positive(value, good=0.0, excellent=0.10)
    if metric == "funds_from_operations_yield":
        return score_positive(value, good=0.025, excellent=0.10)
    if metric == "dividend_yield":
        return _score_sector_dividend_yield(value, sector)
    if metric == "payout_ratio":
        return _score_sustainable_payout(value)
    if metric in {"revenue_growth", "earnings_growth"}:
        return score_positive(value, good=-0.05, excellent=0.25)
    if metric == "return_on_equity":
        return score_positive(value, good=0.0, excellent=0.25)
    if metric == "return_on_assets":
        return score_positive(value, good=0.0, excellent=0.12)
    if metric in {"operating_margins", "profit_margins"}:
        return score_positive(value, good=0.0, excellent=0.25)
    if metric == "debt_to_equity":
        return score_lower_better(value, good=50.0, bad=200.0)
    if metric == "altman_z_score":
        return score_positive(value, good=1.81, excellent=3.0)
    if metric == "beta":
        return score_lower_better(value, good=0.8, bad=1.8)
    return 50.0


def build_sector_fundamental_score(fundamentals: dict[str, Any]) -> dict[str, Any]:
    sector = normalize_sector(fundamentals.get("sector"))
    profile = SECTOR_FUNDAMENTAL_PROFILES[sector]
    components: dict[str, float] = {}
    coverage = 0.0
    weighted_score = 0.0
    for metric, weight in profile.items():
        value = parse_number(fundamentals.get(metric))
        components[metric] = round(score_fundamental_metric(metric, value, sector), 3)
        weighted_score += components[metric] * weight
        if value is not None:
            coverage += weight

    dividend_weight = SECTOR_DIVIDEND_WEIGHTS[sector]
    dividend_quality = build_dividend_quality_score(fundamentals, sector)
    weighted_score = weighted_score * (1 - dividend_weight) + dividend_quality["score"] * dividend_weight
    coverage = coverage * (1 - dividend_weight) + dividend_quality["coverage"] * dividend_weight
    components["dividend_quality"] = dividend_quality["score"]

    combined_weights = {
        **{metric: weight * (1 - dividend_weight) for metric, weight in profile.items()},
        "dividend_quality": dividend_weight,
    }
    leading_metrics = sorted(combined_weights, key=combined_weights.get, reverse=True)[:4]
    return {
        "sector_profile": sector,
        "fundamental_score": round(weighted_score, 3),
        "fundamental_coverage": round(coverage * 100, 1),
        "primary_indicators": ", ".join(METRIC_LABELS[metric] for metric in leading_metrics),
        "component_scores": components,
        "dividend_score": dividend_quality["score"],
        "dividend_coverage": round(dividend_quality["coverage"] * 100, 1),
    }


def sector_profile_frame() -> pd.DataFrame:
    rows = []
    for sector, profile in SECTOR_FUNDAMENTAL_PROFILES.items():
        dividend_weight = SECTOR_DIVIDEND_WEIGHTS[sector]
        rows.append(
            {
                "sector": sector,
                "indicators": ", ".join(
                    [
                        f"{METRIC_LABELS[metric]} ({weight * (1 - dividend_weight):.0%})"
                        for metric, weight in profile.items()
                    ]
                    + [f"Dividend quality/history ({dividend_weight:.0%})"]
                ),
            }
        )
    return pd.DataFrame(rows)


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
    altman_z_score = parse_number(fundamentals.get("altman_z_score"))
    sector_scoring = build_sector_fundamental_score(fundamentals)

    technical_score = (
        score_positive(score, good=-0.01, excellent=0.04) * 0.30
        + score_positive(price_change, good=-0.10, excellent=0.35) * 0.20
        + score_lower_better(volatility, good=0.015, bad=0.08) * 0.20
        + score_rsi(rsi) * 0.15
        + score_direction(technical.get("direction")) * 0.15
    )

    fundamental_score = sector_scoring["fundamental_score"]

    return {
        "symbol": result.get("symbol"),
        "yahoo_symbol": result.get("yahoo_symbol"),
        "name": result.get("name"),
        "country": result.get("country"),
        "market": result.get("universe_market") or result.get("exchange"),
        "exchange": result.get("exchange"),
        "sector": sector_scoring["sector_profile"],
        "reported_sector": fundamentals.get("sector") or "Unknown",
        "industry": fundamentals.get("industry") or "Unknown",
        "direction": technical.get("direction") or "unknown",
        "recommended": scorecard.get("recommended"),
        "technical_score": round(technical_score, 3),
        "fundamental_score": round(fundamental_score, 3),
        "fundamental_coverage": sector_scoring["fundamental_coverage"],
        "dividend_score": sector_scoring["dividend_score"],
        "dividend_coverage": sector_scoring["dividend_coverage"],
        "primary_indicators": sector_scoring["primary_indicators"],
        "score": score,
        "price_change": price_change,
        "volatility": volatility,
        "rsi": rsi,
        "pe_ratio": pe,
        "eps": eps,
        "dividend_yield": dividend,
        "dividend_years_paid": parse_number(fundamentals.get("dividend_years_paid")),
        "consecutive_dividend_years": parse_number(fundamentals.get("consecutive_dividend_years")),
        "dividend_cagr_5y": parse_number(fundamentals.get("dividend_cagr_5y")),
        "beta": beta,
        "revenue_growth": revenue_growth,
        "earnings_growth": earnings_growth,
        "return_on_equity": return_on_equity,
        "debt_to_equity": debt_to_equity,
        "profit_margins": profit_margins,
        "operating_margins": parse_number(fundamentals.get("operating_margins")),
        "return_on_assets": parse_number(fundamentals.get("return_on_assets")),
        "price_to_book": parse_number(fundamentals.get("price_to_book")),
        "enterprise_to_ebitda": parse_number(fundamentals.get("enterprise_to_ebitda")),
        "free_cashflow_yield": parse_number(fundamentals.get("free_cashflow_yield")),
        "funds_from_operations_yield": parse_number(fundamentals.get("funds_from_operations_yield")),
        "payout_ratio": parse_number(fundamentals.get("payout_ratio")),
        "peg_ratio": parse_number(fundamentals.get("peg_ratio")),
        "altman_z_score": altman_z_score,
        "altman_z_zone": fundamentals.get("altman_z_zone") or "Unavailable",
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
    frame["sector_rank"] = (
        frame.groupby("sector")["ranking_score"].rank(method="first", ascending=False).astype(int)
    )
    frame["sector_percentile"] = (
        frame.groupby("sector")["ranking_score"].rank(method="average", pct=True) * 100
    ).round(1)

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
        "altman_z_zone": "altman_z_zone",
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
