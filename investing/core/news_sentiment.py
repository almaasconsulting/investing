from __future__ import annotations

import re

import pandas as pd


POSITIVE_NEWS_TERMS = {
    "accelerate",
    "approval",
    "award",
    "beat",
    "beats",
    "boost",
    "breakthrough",
    "buyback",
    "dividend increase",
    "expansion",
    "gain",
    "gains",
    "growth",
    "higher guidance",
    "improve",
    "improves",
    "outperform",
    "profit",
    "profits",
    "record revenue",
    "raises guidance",
    "recovery",
    "strong demand",
    "surge",
    "upgrade",
}

NEGATIVE_NEWS_TERMS = {
    "bankruptcy",
    "cut guidance",
    "decline",
    "declines",
    "downgrade",
    "fraud",
    "investigation",
    "lawsuit",
    "loss",
    "losses",
    "lower guidance",
    "miss",
    "misses",
    "profit warning",
    "recall",
    "recession",
    "regulatory risk",
    "slump",
    "weak demand",
    "dividend cut",
    "layoff",
    "layoffs",
}


def score_news_text(text: object) -> dict:
    """Score finance-news language with a transparent deterministic lexicon."""
    normalized = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    positive_hits = sorted(
        term
        for term in POSITIVE_NEWS_TERMS
        if re.search(rf"\b{re.escape(term)}\b", normalized)
    )
    negative_hits = sorted(
        term
        for term in NEGATIVE_NEWS_TERMS
        if re.search(rf"\b{re.escape(term)}\b", normalized)
    )
    positive_hits = [
        term
        for term in positive_hits
        if not any(term in negative_term for negative_term in negative_hits)
    ]
    hit_count = len(positive_hits) + len(negative_hits)
    score = (
        (len(positive_hits) - len(negative_hits)) / hit_count
        if hit_count
        else 0.0
    )
    if positive_hits and negative_hits and abs(score) < 0.25:
        label = "Mixed"
    elif score > 0:
        label = "Positive"
    elif score < 0:
        label = "Negative"
    else:
        label = "Neutral"
    return {
        "score": float(score),
        "label": label,
        "positive_hits": positive_hits,
        "negative_hits": negative_hits,
    }


def summarize_stock_news(
    news: pd.DataFrame,
    stocks: pd.DataFrame,
) -> pd.DataFrame:
    """Attach recent-news sentiment and coverage to a stock recommendation list."""
    result = stocks.copy()
    sentiment_columns = {
        "news_sentiment": "Unavailable",
        "news_sentiment_score": float("nan"),
        "news_articles": 0,
        "positive_articles": 0,
        "negative_articles": 0,
        "mixed_articles": 0,
        "neutral_articles": 0,
        "latest_news_title": "",
        "latest_news_url": "",
        "latest_news_at": pd.NaT,
        "news_sentiment_basis": "No recent stored news.",
    }
    for column, default in sentiment_columns.items():
        result[column] = default
    if result.empty or news.empty:
        return result

    prepared = news.copy()
    prepared["symbol_key"] = prepared["symbol"].fillna("").astype(str).str.upper()
    prepared["country_key"] = prepared["country"].fillna("").astype(str).str.lower()
    prepared["published_at"] = pd.to_datetime(
        prepared["published_at"],
        errors="coerce",
    )
    scored = prepared.apply(
        lambda row: score_news_text(
            f"{row.get('title', '')}. {row.get('summary', '')}"
        ),
        axis=1,
    )
    prepared["article_sentiment"] = scored.map(lambda value: value["label"])
    prepared["article_sentiment_score"] = scored.map(lambda value: value["score"])

    for index, stock in result.iterrows():
        symbol = str(stock.get("symbol", "")).upper()
        country = str(stock.get("country", "")).lower()
        articles = prepared[
            (prepared["symbol_key"] == symbol)
            & (prepared["country_key"] == country)
        ].sort_values("published_at", ascending=False, na_position="last")
        if articles.empty:
            continue
        counts = articles["article_sentiment"].value_counts()
        average_score = float(articles["article_sentiment_score"].mean())
        positive = int(counts.get("Positive", 0))
        negative = int(counts.get("Negative", 0))
        mixed = int(counts.get("Mixed", 0))
        neutral = int(counts.get("Neutral", 0))
        if positive and negative and abs(average_score) < 0.15:
            aggregate_label = "Mixed"
        elif average_score > 0.15:
            aggregate_label = "Positive"
        elif average_score < -0.15:
            aggregate_label = "Negative"
        else:
            aggregate_label = "Neutral"
        latest = articles.iloc[0]
        result.at[index, "news_sentiment"] = aggregate_label
        result.at[index, "news_sentiment_score"] = average_score
        result.at[index, "news_articles"] = len(articles)
        result.at[index, "positive_articles"] = positive
        result.at[index, "negative_articles"] = negative
        result.at[index, "mixed_articles"] = mixed
        result.at[index, "neutral_articles"] = neutral
        result.at[index, "latest_news_title"] = str(latest.get("title") or "")
        result.at[index, "latest_news_url"] = str(latest.get("url") or "")
        result.at[index, "latest_news_at"] = latest.get("published_at")
        result.at[index, "news_sentiment_basis"] = (
            f"{positive} positive, {negative} negative, {mixed} mixed, "
            f"{neutral} neutral article(s)"
        )
    return result
