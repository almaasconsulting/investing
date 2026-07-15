from __future__ import annotations

import pandas as pd


def compute_stock_metrics(df: pd.DataFrame) -> dict:
    df = df.sort_values("date").copy()
    df["return"] = df["close"].pct_change()
    avg_daily_return = float(df["return"].mean())
    volatility = float(df["return"].std())
    price_change = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1)

    score = 0.0
    if volatility > 0:
        score = avg_daily_return / volatility

    return {
        "average_daily_return": avg_daily_return,
        "volatility": volatility,
        "price_change": price_change,
        "score": score,
        "latest_close": float(df["close"].iat[-1]),
        "data_points": len(df),
    }


def build_scorecard(metrics: dict, min_score: float = 0.01, max_volatility: float = 0.06) -> dict:
    recommended = metrics["score"] >= min_score and metrics["volatility"] <= max_volatility
    return {
        "recommended": recommended,
        "reason": (
            "Meets conservative score/volatility thresholds"
            if recommended
            else "Does not meet score or volatility thresholds"
        ),
        **metrics,
    }
