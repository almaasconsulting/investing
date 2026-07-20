from __future__ import annotations

import base64
import importlib
from dataclasses import replace

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from investing.core.clustering import (
    build_close_price_matrix,
    cluster_by_correlation,
    compute_return_correlation,
    correlation_pairs,
)
from investing.core.html_report import generate_watchlist_report
import investing.core.ranking as ranking_module

# Streamlit can retain imported application modules across source hot reloads.
# Reload when the cached ranking API predates fields required by this UI.
if getattr(ranking_module, "RANKING_API_VERSION", 0) < 3:
    ranking_module = importlib.reload(ranking_module)

build_rankings = ranking_module.build_rankings
build_sector_fundamental_score = ranking_module.build_sector_fundamental_score
parse_number = ranking_module.parse_number
sector_profile_frame = ranking_module.sector_profile_frame
top_stocks_by_country_sector = ranking_module.top_stocks_by_country_sector
score_direction = ranking_module.score_direction
score_lower_better = ranking_module.score_lower_better
score_pe = ranking_module.score_pe
score_positive = ranking_module.score_positive
score_rsi = ranking_module.score_rsi
import investing.core.portfolio as portfolio_module
import investing.core.watchlist as watchlist_module
from investing.data_fetch.stock_universe import DEFAULT_MARKET_COUNTRIES

# Pipeline updates added incremental fetch arguments to the portfolio service.
# Reload both it and its watchlist consumer when Streamlit cached the old API.
if getattr(portfolio_module, "PORTFOLIO_API_VERSION", 0) < 3:
    portfolio_module = importlib.reload(portfolio_module)
    watchlist_module = importlib.reload(watchlist_module)

from investing.core.watchlist import (
    WATCHLIST_FIELDS,
    analyze_watchlist,
    append_watchlist_rows,
    read_watchlist,
    write_watchlist,
)
from investing.db.store import (
    init_db,
    query_financial_statement_trends,
    query_latest_analysis_snapshots,
    query_stock_news,
    query_stock_universe,
)
import investing.pipeline.config as pipeline_config_module
import investing.pipeline.updates as pipeline_updates_module

# Streamlit retains imported modules across source reruns. Reload the pipeline
# service and its settings class when the cached API predates incremental fields.
if getattr(pipeline_updates_module, "PIPELINE_API_VERSION", 0) < 4:
    pipeline_config_module = importlib.reload(pipeline_config_module)
    pipeline_updates_module = importlib.reload(pipeline_updates_module)

PipelineSettings = pipeline_config_module.PipelineSettings
pipeline_analyze_universe_frame = pipeline_updates_module.analyze_universe_frame
pipeline_build_medallion = pipeline_updates_module.build_medallion
pipeline_persist_analysis_results = pipeline_updates_module.persist_analysis_results
pipeline_refresh_stock_universe = pipeline_updates_module.refresh_stock_universe
pipeline_refresh_stock_intelligence = pipeline_updates_module.refresh_stock_intelligence


@st.cache_data(ttl=300, show_spinner=False)
def load_stock_news(symbol: str, country: str) -> pd.DataFrame:
    return query_stock_news(symbol, country=country, limit=50)


@st.cache_data(ttl=300, show_spinner=False)
def load_statement_trends(
    symbol: str,
    country: str,
    period_type: str,
) -> pd.DataFrame:
    return query_financial_statement_trends(
        symbol,
        country=country,
        period_type=period_type,
    )


FUNDAMENTAL_TREND_METRICS = [
    "revenue",
    "gross_profit",
    "operating_income",
    "ebitda",
    "net_income",
    "diluted_eps",
    "operating_cash_flow",
    "capital_expenditure",
    "free_cash_flow",
    "cash_and_equivalents",
    "total_debt",
    "stockholders_equity",
]


def render_statement_history(frame: pd.DataFrame, period_label: str) -> None:
    if frame.empty:
        st.info(f"No {period_label.lower()} statement history has been ingested yet.")
        return
    available = frame["canonical_line_item"].dropna().astype(str).unique().tolist()
    defaults = [metric for metric in FUNDAMENTAL_TREND_METRICS if metric in available][:5]
    selected = st.multiselect(
        f"{period_label} metrics",
        sorted(available),
        default=defaults,
        key=f"statement_metrics_{period_label.lower()}",
    )
    filtered = frame[frame["canonical_line_item"].isin(selected)] if selected else frame
    if selected:
        chart = filtered.pivot_table(
            index="fiscal_period_end",
            columns="canonical_line_item",
            values="value",
            aggfunc="last",
        ).sort_index()
        st.line_chart(chart, width="stretch")
    display_columns = [
        "fiscal_period_end", "canonical_line_item", "value", "currency",
        "period_change_pct", "year_over_year_pct", "selected_source",
    ]
    display_columns = [column for column in display_columns if column in filtered.columns]
    display = filtered[display_columns].sort_values(
        ["fiscal_period_end", "canonical_line_item"], ascending=[False, True]
    )
    formatters = {
        "value": "{:,.2f}",
        "period_change_pct": "{:+.1f}%",
        "year_over_year_pct": "{:+.1f}%",
    }
    st.dataframe(
        display.style.format(
            {key: value for key, value in formatters.items() if key in display.columns},
            na_rep="n/a",
        ),
        width="stretch",
        hide_index=True,
    )


def split_csv(value: str) -> list[str]:
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def universe_display(row: pd.Series) -> str:
    yahoo = row.get("yahoo_symbol", "")
    market = row.get("exchange_mic") or row.get("market") or row.get("exchange") or ""
    name = row.get("name", "")
    return f"{row['symbol']} | {yahoo} | {market} | {name}"


def selected_rows(universe: pd.DataFrame, labels: list[str]) -> pd.DataFrame:
    if not labels:
        return universe.iloc[0:0]
    label_to_index = {universe_display(row): index for index, row in universe.iterrows()}
    indexes = [label_to_index[label] for label in labels if label in label_to_index]
    return universe.loc[indexes]


def filter_universe_by_search(universe: pd.DataFrame, query: str) -> pd.DataFrame:
    query = query.strip().lower()
    if not query:
        return universe

    search_columns = [
        column
        for column in ["symbol", "yahoo_symbol", "name", "full_name", "isin"]
        if column in universe.columns
    ]
    if not search_columns:
        return universe

    mask = pd.Series(False, index=universe.index)
    for column in search_columns:
        mask = mask | universe[column].fillna("").astype(str).str.lower().str.contains(query, regex=False)
    return universe[mask]


def rows_from_results(results: list[dict]) -> pd.DataFrame:
    rows = []
    for result in results:
        if result.get("error"):
            continue
        rows.append(
            {
                "symbol": result.get("symbol"),
                "country": result.get("country", "norway"),
            }
        )
    return pd.DataFrame(rows)


def selected_symbols(universe: pd.DataFrame) -> list[str]:
    if universe.empty or "symbol" not in universe.columns:
        return []
    return universe["symbol"].dropna().astype(str).tolist()


def format_timestamp(value: object) -> str:
    if value is None or value == "":
        return ""
    try:
        timestamp = pd.to_datetime(value)
        if pd.isna(timestamp):
            return ""
        return timestamp.strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return str(value)


def format_decimal(value: object, digits: int = 3) -> str:
    try:
        if value is None or pd.isna(value):
            return "n/a"
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def format_percent(value: object, digits: int = 2) -> str:
    try:
        if value is None or pd.isna(value):
            return "n/a"
        return f"{float(value):.{digits}%}"
    except (TypeError, ValueError):
        return "n/a"


def round_numeric_frame(frame: pd.DataFrame, digits: int = 3) -> pd.DataFrame:
    rounded = frame.copy()
    for column in rounded.columns:
        if pd.api.types.is_numeric_dtype(rounded[column]):
            rounded[column] = rounded[column].round(digits)
    return rounded


RATIO_PERCENT_COLUMNS = {
    "average_daily_return",
    "volatility",
    "price_change",
    "dividend_yield",
    "dividend_cagr_5y",
    "revenue_growth",
    "earnings_growth",
    "return_on_equity",
    "return_on_assets",
    "profit_margins",
    "operating_margins",
    "gross_margins",
    "free_cashflow_yield",
    "funds_from_operations_yield",
    "payout_ratio",
    "one_year_change",
}
PERCENT_POINT_COLUMNS = {
    "fundamental_coverage",
    "dividend_coverage",
    "sector_percentile",
}

FIELD_LABELS = {
    "latest_close": "Latest close",
    "prev_close": "Previous close",
    "ma20": "20-day moving average",
    "ma50": "50-day moving average",
    "ma200": "200-day moving average",
    "rsi": "RSI",
    "rsi14": "RSI (14-day)",
    "signal_summary": "Signal summary",
    "price_source": "Price source",
    "market_cap": "Market capitalization",
    "pe_ratio": "P/E ratio",
    "eps": "Earnings per share (EPS)",
    "one_year_change": "One-year change",
    "shares_outstanding": "Shares outstanding",
    "revenue_growth": "Revenue growth",
    "earnings_growth": "Earnings growth",
    "return_on_equity": "Return on equity",
    "return_on_assets": "Return on assets",
    "profit_margins": "Net profit margin",
    "operating_margins": "Operating margin",
    "gross_margins": "Gross margin",
    "debt_to_equity": "Debt-to-equity ratio",
    "current_ratio": "Current ratio",
    "free_cashflow": "Free cash flow",
    "free_cashflow_yield": "Free-cash-flow yield",
    "price_to_book": "Price-to-book ratio",
    "enterprise_to_ebitda": "EV/EBITDA",
    "peg_ratio": "PEG ratio",
    "payout_ratio": "Payout ratio",
    "funds_from_operations": "Funds from operations (FFO)",
    "funds_from_operations_yield": "FFO yield",
    "consecutive_dividend_years": "Consecutive dividend years",
    "dividend_cagr_5y": "Five-year dividend growth",
    "altman_z_score": "Altman Z-score",
    "data_source": "Data source",
}

COMPACT_NUMBER_FIELDS = {
    "market_cap",
    "shares_outstanding",
    "revenue",
    "free_cashflow",
    "funds_from_operations",
}
PRICE_FIELDS = {"latest_close", "prev_close", "ma20", "ma50", "ma200", "eps"}
ONE_DECIMAL_FIELDS = {"rsi", "rsi14", "score"}
TWO_DECIMAL_FIELDS = {
    "pe_ratio",
    "beta",
    "debt_to_equity",
    "current_ratio",
    "price_to_book",
    "enterprise_to_ebitda",
    "peg_ratio",
    "altman_z_score",
}
INTEGER_FIELDS = {"consecutive_dividend_years", "dividend_years"}


def format_field_label(key: object) -> str:
    field = str(key).strip()
    if field in FIELD_LABELS:
        return FIELD_LABELS[field]
    words = field.replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else "Field"


def format_compact_number(value: object) -> str:
    parsed = parse_number(value)
    if parsed is None:
        return "n/a"
    magnitude = abs(parsed)
    for threshold, suffix in (
        (1_000_000_000_000, "T"),
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    ):
        if magnitude >= threshold:
            return f"{parsed / threshold:,.2f}{suffix}"
    return f"{parsed:,.0f}"


def format_price(value: object) -> str:
    parsed = parse_number(value)
    if parsed is None:
        return "n/a"
    digits = 4 if abs(parsed) < 1 else 3 if abs(parsed) < 100 else 2
    return f"{parsed:,.{digits}f}"


def format_detail_value(key: str, value: object) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "n/a"
    if key in RATIO_PERCENT_COLUMNS:
        return format_percent(parse_number(value), digits=2)
    if key in PERCENT_POINT_COLUMNS:
        parsed = parse_number(value)
        return f"{parsed:.1f}%" if parsed is not None else "n/a"
    if key in COMPACT_NUMBER_FIELDS:
        return format_compact_number(value)
    if key in PRICE_FIELDS:
        return format_price(value)
    if key in INTEGER_FIELDS:
        parsed = parse_number(value)
        return f"{parsed:,.0f}" if parsed is not None else "n/a"
    if key in ONE_DECIMAL_FIELDS:
        parsed = parse_number(value)
        return f"{parsed:,.1f}" if parsed is not None else "n/a"
    if key in TWO_DECIMAL_FIELDS:
        parsed = parse_number(value)
        return f"{parsed:,.2f}" if parsed is not None else "n/a"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return f"{float(value):,.2f}"
    return str(value)


def style_numeric_frame(frame: pd.DataFrame, digits: int = 3) -> pd.io.formats.style.Styler:
    """Format financial ratios as percentages without changing their values."""
    rounded = round_numeric_frame(frame, digits=digits)
    formatters = {
        column: "{:.2%}"
        for column in RATIO_PERCENT_COLUMNS.intersection(rounded.columns)
        if pd.api.types.is_numeric_dtype(rounded[column])
    }
    formatters.update(
        {
            column: "{:.1f}%"
            for column in PERCENT_POINT_COLUMNS.intersection(rounded.columns)
            if pd.api.types.is_numeric_dtype(rounded[column])
        }
    )
    return rounded.style.format(formatters, na_rep="")


def detail_frame(values: dict) -> pd.DataFrame:
    rows = [
        {
            "Indicator": format_field_label(key),
            "Value": format_detail_value(str(key), value),
        }
        for key, value in values.items()
    ]
    return pd.DataFrame(rows, dtype="string")


def render_detail_panel(
    title: str,
    description: str,
    values: dict,
    *,
    height: int | None = None,
) -> None:
    frame = detail_frame(values)
    table_height = height or min(520, 38 + max(len(frame), 1) * 35)
    with st.container(border=True):
        st.markdown(f"#### {title}")
        st.caption(description)
        st.dataframe(
            frame,
            width="stretch",
            hide_index=True,
            height=table_height,
            column_config={
                "Indicator": st.column_config.TextColumn("Indicator", width="medium"),
                "Value": st.column_config.TextColumn("Value", width="large"),
            },
        )


def numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(index=frame.index, dtype=float)
    return frame[column].map(parse_number).astype(float)


def text_options(frame: pd.DataFrame, column: str) -> list[str]:
    if column not in frame.columns:
        return []
    values = frame[column].dropna().astype(str).str.strip()
    return sorted(value for value in values.unique().tolist() if value and value.lower() != "nan")


def apply_min_filter(frame: pd.DataFrame, column: str, threshold: float) -> pd.DataFrame:
    values = numeric_series(frame, column)
    return frame[values.notna() & (values >= threshold)]


def apply_max_filter(frame: pd.DataFrame, column: str, threshold: float) -> pd.DataFrame:
    values = numeric_series(frame, column)
    return frame[values.notna() & (values <= threshold)]


def apply_range_filter(frame: pd.DataFrame, column: str, lower: float, upper: float) -> pd.DataFrame:
    values = numeric_series(frame, column)
    return frame[values.notna() & values.between(lower, upper)]


def analysis_filter_controls(frame: pd.DataFrame) -> pd.DataFrame:
    filtered = frame.copy()

    query = st.text_input("Search analyzed ticker or company", value="", key="analysis_filter_search")
    if query.strip():
        filtered = filter_universe_by_search(filtered, query)

    direction_options = text_options(frame, "direction")
    selected_directions = st.multiselect(
        "Technical direction",
        direction_options,
        default=direction_options,
        key="analysis_filter_direction",
    )
    if direction_options and set(selected_directions) != set(direction_options):
        filtered = filtered[filtered["direction"].astype(str).isin(selected_directions)]

    recommendation_options = text_options(frame, "recommended")
    selected_recommendations = st.multiselect(
        "Recommendation",
        recommendation_options,
        default=recommendation_options,
        key="analysis_filter_recommendation",
    )
    if recommendation_options and set(selected_recommendations) != set(recommendation_options):
        filtered = filtered[filtered["recommended"].astype(str).isin(selected_recommendations)]

    sector_options = text_options(frame, "sector")
    selected_sectors = st.multiselect("Sector", sector_options, default=[], key="analysis_filter_sector")
    if selected_sectors:
        filtered = filtered[filtered["sector"].astype(str).isin(selected_sectors)]

    industry_options = text_options(frame, "industry")
    selected_industries = st.multiselect("Industry", industry_options, default=[], key="analysis_filter_industry")
    if selected_industries:
        filtered = filtered[filtered["industry"].astype(str).isin(selected_industries)]

    st.caption("Technical criteria")
    if st.checkbox("Score >=", value=False, key="analysis_filter_use_score"):
        threshold = st.number_input("Minimum score", value=0.0, step=0.01, format="%.3f", key="analysis_filter_score")
        filtered = apply_min_filter(filtered, "score", threshold)

    if st.checkbox("Volatility <=", value=False, key="analysis_filter_use_volatility"):
        threshold = st.number_input("Maximum volatility %", value=6.0, step=1.0, format="%.2f", key="analysis_filter_volatility")
        filtered = apply_max_filter(filtered, "volatility", threshold / 100)

    if st.checkbox("Price change >=", value=False, key="analysis_filter_use_price_change"):
        threshold = st.number_input("Minimum price change %", value=0.0, step=1.0, format="%.3f", key="analysis_filter_price_change")
        filtered = apply_min_filter(filtered, "price_change", threshold / 100)

    if st.checkbox("RSI range", value=False, key="analysis_filter_use_rsi"):
        lower, upper = st.slider("RSI", min_value=0.0, max_value=100.0, value=(0.0, 100.0), step=1.0, key="analysis_filter_rsi")
        filtered = apply_range_filter(filtered, "rsi", lower, upper)

    st.caption("Fundamental criteria")
    if st.checkbox("Sector fundamental score >=", value=False, key="analysis_filter_use_fundamental_score"):
        threshold = st.number_input(
            "Minimum sector fundamental score",
            min_value=0.0,
            max_value=100.0,
            value=50.0,
            step=5.0,
            key="analysis_filter_fundamental_score",
        )
        filtered = apply_min_filter(filtered, "sector_fundamental_score", threshold)

    if st.checkbox("Fundamental data coverage >=", value=False, key="analysis_filter_use_fundamental_coverage"):
        threshold = st.number_input(
            "Minimum fundamental coverage %",
            min_value=0.0,
            max_value=100.0,
            value=60.0,
            step=5.0,
            key="analysis_filter_fundamental_coverage",
        )
        filtered = apply_min_filter(filtered, "fundamental_coverage", threshold)

    if st.checkbox("P/E <=", value=False, key="analysis_filter_use_pe"):
        threshold = st.number_input("Maximum P/E", value=25.0, step=1.0, format="%.3f", key="analysis_filter_pe")
        filtered = apply_max_filter(filtered, "pe_ratio", threshold)

    if st.checkbox("Dividend yield >=", value=False, key="analysis_filter_use_dividend"):
        threshold = st.number_input("Minimum dividend yield %", value=0.0, step=0.5, format="%.3f", key="analysis_filter_dividend")
        filtered = apply_min_filter(filtered, "dividend_yield", threshold / 100)

    if st.checkbox("Dividend quality score >=", value=False, key="analysis_filter_use_dividend_score"):
        threshold = st.number_input(
            "Minimum dividend quality score",
            min_value=0.0,
            max_value=100.0,
            value=50.0,
            step=5.0,
            key="analysis_filter_dividend_score",
        )
        filtered = apply_min_filter(filtered, "dividend_score", threshold)

    if st.checkbox("Consecutive dividend years >=", value=False, key="analysis_filter_use_dividend_years"):
        threshold = st.number_input(
            "Minimum consecutive dividend years",
            min_value=0,
            value=5,
            step=1,
            key="analysis_filter_dividend_years",
        )
        filtered = apply_min_filter(filtered, "consecutive_dividend_years", threshold)

    if st.checkbox("Revenue growth >=", value=False, key="analysis_filter_use_revenue_growth"):
        threshold = st.number_input("Minimum revenue growth %", value=0.0, step=1.0, format="%.3f", key="analysis_filter_revenue_growth")
        filtered = apply_min_filter(filtered, "revenue_growth", threshold / 100)

    if st.checkbox("Earnings growth >=", value=False, key="analysis_filter_use_earnings_growth"):
        threshold = st.number_input("Minimum earnings growth %", value=0.0, step=1.0, format="%.3f", key="analysis_filter_earnings_growth")
        filtered = apply_min_filter(filtered, "earnings_growth", threshold / 100)

    if st.checkbox("Return on equity >=", value=False, key="analysis_filter_use_roe"):
        threshold = st.number_input("Minimum return on equity %", value=0.0, step=1.0, format="%.3f", key="analysis_filter_roe")
        filtered = apply_min_filter(filtered, "return_on_equity", threshold / 100)

    if st.checkbox("Debt/equity <=", value=False, key="analysis_filter_use_debt"):
        threshold = st.number_input("Maximum debt/equity", value=200.0, step=10.0, format="%.3f", key="analysis_filter_debt")
        filtered = apply_max_filter(filtered, "debt_to_equity", threshold)

    altman_z_zones = text_options(frame, "altman_z_zone")
    selected_altman_z_zones = st.multiselect(
        "Altman Z-score zone",
        altman_z_zones,
        default=altman_z_zones,
        key="analysis_filter_altman_z_zone",
    )
    if altman_z_zones and set(selected_altman_z_zones) != set(altman_z_zones):
        filtered = filtered[filtered["altman_z_zone"].astype(str).isin(selected_altman_z_zones)]

    if st.checkbox("Altman Z-score >=", value=False, key="analysis_filter_use_altman_z"):
        threshold = st.number_input(
            "Minimum Altman Z-score",
            value=1.81,
            step=0.1,
            format="%.3f",
            key="analysis_filter_altman_z",
        )
        filtered = apply_min_filter(filtered, "altman_z_score", threshold)

    st.caption(f"{len(filtered)} of {len(frame)} analyzed stocks match")
    return filtered


def filter_results_by_frame(results: list[dict], frame: pd.DataFrame) -> list[dict]:
    keys = {
        (str(row.get("symbol", "")), str(row.get("country", "")))
        for row in frame.to_dict("records")
    }
    return [
        result
        for result in results
        if (str(result.get("symbol", "")), str(result.get("country", ""))) in keys
    ]


def reset_analysis_filter_state() -> None:
    """Discard stale widget selections when a different saved result set is loaded."""
    for key in list(st.session_state):
        if str(key).startswith("analysis_filter_"):
            del st.session_state[key]


SPIDER_METRICS = [
    "Trend",
    "Momentum",
    "Risk",
    "RSI",
    "Valuation",
    "Yield",
    "Growth",
    "Profitability",
    "Balance Sheet",
]


def average_score(*scores: float) -> float:
    return sum(scores) / len(scores)


def spider_scores(result: dict) -> dict[str, float]:
    scorecard = result.get("scorecard", {})
    technical = result.get("technical", {})
    fundamentals = result.get("fundamentals", {})

    price_change = parse_number(scorecard.get("price_change"))
    volatility = parse_number(scorecard.get("volatility"))
    rsi = parse_number(technical.get("rsi"))
    pe = parse_number(fundamentals.get("pe_ratio"))
    dividend = parse_number(fundamentals.get("dividend_yield"))
    revenue_growth = parse_number(fundamentals.get("revenue_growth"))
    earnings_growth = parse_number(fundamentals.get("earnings_growth"))
    return_on_equity = parse_number(fundamentals.get("return_on_equity"))
    profit_margins = parse_number(fundamentals.get("profit_margins"))
    debt_to_equity = parse_number(fundamentals.get("debt_to_equity"))

    return {
        "Trend": score_direction(technical.get("direction")),
        "Momentum": score_positive(price_change, good=-0.10, excellent=0.35),
        "Risk": score_lower_better(volatility, good=0.015, bad=0.08),
        "RSI": score_rsi(rsi),
        "Valuation": score_pe(pe),
        "Yield": score_positive(dividend, good=0, excellent=0.06),
        "Growth": average_score(
            score_positive(revenue_growth, good=-0.05, excellent=0.25),
            score_positive(earnings_growth, good=-0.05, excellent=0.25),
        ),
        "Profitability": average_score(
            score_positive(return_on_equity, good=0, excellent=0.20),
            score_positive(profit_margins, good=0, excellent=0.20),
        ),
        "Balance Sheet": average_score(
            score_lower_better(debt_to_equity, good=40, bad=200),
            score_positive(parse_number(fundamentals.get("altman_z_score")), good=1.81, excellent=3.0),
        ),
    }


def spider_frame(results: list[dict]) -> pd.DataFrame:
    rows = []
    for result in results:
        if result.get("error"):
            continue
        rows.append(
            {
                "symbol": result.get("symbol"),
                "name": result.get("name"),
                **spider_scores(result),
            }
        )
    return pd.DataFrame(rows)


def build_spider_chart(frame: pd.DataFrame, selected_symbols: list[str]) -> go.Figure:
    fig = go.Figure()
    selected = frame[frame["symbol"].isin(selected_symbols)]
    theta = SPIDER_METRICS + [SPIDER_METRICS[0]]
    for _, row in selected.iterrows():
        values = [float(row[metric]) for metric in SPIDER_METRICS]
        values.append(values[0])
        fig.add_trace(
            go.Scatterpolar(
                r=values,
                theta=theta,
                fill="toself",
                mode="lines+markers",
                name=str(row["symbol"]),
            )
        )
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        height=620,
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=True,
    )
    return fig


def analyze_universe(universe: pd.DataFrame, days: int, min_score: float, max_volatility: float, data_source: str) -> list[dict]:
    return pipeline_analyze_universe_frame(
        universe,
        days=days,
        min_score=min_score,
        max_volatility=max_volatility,
        data_source=data_source,
    )


def scorecard_frame(results: list[dict]) -> pd.DataFrame:
    rows = []
    for result in results:
        if result.get("error"):
            rows.append({"symbol": result.get("symbol"), "error": result.get("error")})
            continue
        scorecard = result.get("scorecard", {})
        technical = result.get("technical", {})
        fundamentals = result.get("fundamentals", {})
        sector_scoring = build_sector_fundamental_score(fundamentals)
        rows.append(
            {
                "symbol": result.get("symbol"),
                "yahoo_symbol": result.get("yahoo_symbol"),
                "name": result.get("name"),
                "country": result.get("country"),
                "exchange": result.get("exchange"),
                "data_source": result.get("data_source"),
                "fundamental_data_source": result.get("fundamental_data_source"),
                "last_run_at": format_timestamp(result.get("last_run_at")),
                "cached": bool(result.get("cached", False)),
                "recommended": scorecard.get("recommended"),
                "score": parse_number(scorecard.get("score")),
                "volatility": parse_number(scorecard.get("volatility")),
                "price_change": parse_number(scorecard.get("price_change")),
                "latest_close": parse_number(scorecard.get("latest_close")),
                "direction": technical.get("direction"),
                "rsi": parse_number(technical.get("rsi")),
                "pe_ratio": parse_number(fundamentals.get("pe_ratio")),
                "dividend_yield": parse_number(fundamentals.get("dividend_yield")),
                "dividend_score": sector_scoring.get("dividend_score"),
                "dividend_coverage": sector_scoring.get("dividend_coverage"),
                "dividend_years_paid": parse_number(fundamentals.get("dividend_years_paid")),
                "consecutive_dividend_years": parse_number(fundamentals.get("consecutive_dividend_years")),
                "dividend_cagr_5y": parse_number(fundamentals.get("dividend_cagr_5y")),
                "sector": fundamentals.get("sector"),
                "industry": fundamentals.get("industry"),
                "sector_fundamental_score": sector_scoring.get("fundamental_score"),
                "fundamental_coverage": sector_scoring.get("fundamental_coverage"),
                "revenue_growth": parse_number(fundamentals.get("revenue_growth")),
                "earnings_growth": parse_number(fundamentals.get("earnings_growth")),
                "return_on_equity": parse_number(fundamentals.get("return_on_equity")),
                "profit_margins": parse_number(fundamentals.get("profit_margins")),
                "debt_to_equity": parse_number(fundamentals.get("debt_to_equity")),
                "current_ratio": parse_number(fundamentals.get("current_ratio")),
                "free_cashflow": parse_number(fundamentals.get("free_cashflow")),
                "free_cashflow_yield": parse_number(fundamentals.get("free_cashflow_yield")),
                "price_to_book": parse_number(fundamentals.get("price_to_book")),
                "enterprise_to_ebitda": parse_number(fundamentals.get("enterprise_to_ebitda")),
                "peg_ratio": parse_number(fundamentals.get("peg_ratio")),
                "payout_ratio": parse_number(fundamentals.get("payout_ratio")),
                "return_on_assets": parse_number(fundamentals.get("return_on_assets")),
                "operating_margins": parse_number(fundamentals.get("operating_margins")),
                "funds_from_operations_yield": parse_number(fundamentals.get("funds_from_operations_yield")),
                "altman_z_score": parse_number(fundamentals.get("altman_z_score")),
                "altman_z_zone": fundamentals.get("altman_z_zone") or "Unavailable",
                "error": "",
            }
        )
    return pd.DataFrame(rows)


def store_analysis_results(
    results: list[dict],
    fallback_source: str,
    days: int,
    min_score: float,
    max_volatility: float,
) -> tuple[int, int]:
    persisted = pipeline_persist_analysis_results(
        results,
        days=days,
        min_score=min_score,
        max_volatility=max_volatility,
        fallback_source=fallback_source,
    )
    pipeline_build_medallion()
    return persisted["price_histories"], persisted["analysis_snapshots"]


@st.cache_data(ttl=300, show_spinner=False)
def load_saved_analysis_for_rows(
    universe: pd.DataFrame,
    *,
    include_history: bool = False,
) -> list[dict]:
    """Load lightweight snapshots; individual history is loaded in Stock View."""
    return query_latest_analysis_snapshots(
        countries=universe["country"].dropna().astype(str).unique().tolist(),
        symbols=selected_symbols(universe),
        include_history=include_history,
    )


def load_sector_metadata_for_rows(universe: pd.DataFrame) -> pd.DataFrame:
    if universe.empty:
        return pd.DataFrame(columns=["symbol", "country", "sector", "industry", "last_run_at"])

    snapshots = query_latest_analysis_snapshots(
        countries=universe["country"].dropna().astype(str).unique().tolist(),
        symbols=selected_symbols(universe),
        include_history=False,
    )
    rows = []
    for result in snapshots:
        fundamentals = result.get("fundamentals", {})
        sector = str(fundamentals.get("sector") or "").strip()
        industry = str(fundamentals.get("industry") or "").strip()
        rows.append(
            {
                "symbol": str(result.get("symbol", "")).upper(),
                "country": str(result.get("country", "")).lower(),
                "sector": sector if sector and sector.lower() != "none" else "Unknown",
                "industry": industry if industry and industry.lower() != "none" else "Unknown",
                "last_run_at": result.get("last_run_at"),
            }
        )
    return pd.DataFrame(rows)


def rows_for_selected_sectors(universe: pd.DataFrame, sector_frame: pd.DataFrame, sectors: list[str]) -> pd.DataFrame:
    if universe.empty or sector_frame.empty or not sectors:
        return universe.iloc[0:0]

    selected = sector_frame[sector_frame["sector"].isin(sectors)]
    keys = {
        (row["symbol"], row["country"])
        for row in selected[["symbol", "country"]].to_dict("records")
    }
    normalized = universe.assign(
        _symbol=universe["symbol"].fillna("").astype(str).str.upper(),
        _country=universe["country"].fillna("").astype(str).str.lower(),
    )
    mask = normalized.apply(lambda row: (row["_symbol"], row["_country"]) in keys, axis=1)
    return universe[mask]


def rows_for_watchlist(universe: pd.DataFrame, notes: str = "") -> list[dict]:
    rows = []
    for row in universe.itertuples(index=False):
        rows.append(
            {
                "symbol": row.symbol,
                "country": row.country,
                "exchange": row.exchange_mic or row.market or row.exchange,
                "name": row.name,
                "notes": notes,
            }
        )
    return rows


def format_cli_report(results: list[dict], fallback_source: str) -> str:
    lines: list[str] = []
    for result in results:
        symbol = result.get("symbol", "")
        if result.get("error"):
            lines.append(f"{symbol}: ERROR - {result['error']}")
            continue

        scorecard = result.get("scorecard", {})
        technical = result.get("technical", {})
        fundamentals = result.get("fundamentals", {})
        lines.extend(
            [
                f"{symbol} ({result.get('name', '')})",
                f" Country: {result.get('country', '')} | Exchange: {result.get('exchange', '')}",
                f" Data source: {result.get('data_source', fallback_source)} | Yahoo: {result.get('yahoo_symbol', '')}",
                f" Fundamental source: {result.get('fundamental_data_source', fallback_source)}",
                f" Recommended: {scorecard.get('recommended')} | Reason: {scorecard.get('reason')}",
                f" Score: {format_decimal(scorecard.get('score'))} | Volatility: {format_percent(scorecard.get('volatility'))}",
                f" Price change: {format_percent(scorecard.get('price_change'))} | Latest close: {format_decimal(scorecard.get('latest_close'))}",
                f" Technical direction: {technical.get('direction', 'n/a')} | Signal: {technical.get('signal_summary', 'n/a')}",
            ]
        )
        if fundamentals:
            sector_scoring = build_sector_fundamental_score(fundamentals)
            lines.append(
                " Fundamental P/E: "
                f"{fundamentals.get('pe_ratio', 'n/a')} | EPS: {fundamentals.get('eps', 'n/a')} | "
                f"Dividend yield: {format_percent(parse_number(fundamentals.get('dividend_yield')))} | "
                f"Altman Z: {fundamentals.get('altman_z_score', 'n/a')} "
                f"({fundamentals.get('altman_z_zone', 'Unavailable')})"
            )
            lines.append(
                f" Sector fundamentals: {sector_scoring['fundamental_score']:.3f}/100 | "
                f"Profile: {sector_scoring['sector_profile']} | "
                f"Coverage: {sector_scoring['fundamental_coverage']:.1f}%"
            )
            lines.append(
                f" Dividend quality: {format_decimal(sector_scoring.get('dividend_score'))}/100 | "
                f"Years paid: {fundamentals.get('dividend_years_paid', 'n/a')} | "
                f"Consecutive years: {fundamentals.get('consecutive_dividend_years', 'n/a')}"
            )
        lines.append("")
    return "\n".join(lines).strip()


def build_correlation_groups(universe: pd.DataFrame, days: int, data_source: str, min_correlation: float) -> tuple[dict[str, str], dict]:
    symbol_list = universe["symbol"].dropna().astype(str).tolist()
    country_map = dict(zip(universe["symbol"], universe["country"]))
    price_matrix, errors = build_close_price_matrix(
        symbol_list,
        country_by_symbol=country_map,
        days=days,
        data_source=data_source,
    )
    correlation = compute_return_correlation(price_matrix)
    clusters = cluster_by_correlation(correlation, min_correlation=min_correlation)
    cluster_map = {
        row.symbol: f"Cluster {row.cluster}"
        for row in clusters.itertuples(index=False)
    }
    return cluster_map, {
        "prices": price_matrix,
        "correlation": correlation,
        "clusters": clusters,
        "pairs": correlation_pairs(correlation) if not correlation.empty else pd.DataFrame(),
        "errors": errors,
    }


st.set_page_config(page_title="Investing Workbench", layout="wide")
_startup_connection = init_db()
_startup_connection.close()


@st.fragment(run_every="30s")
def refresh_postgresql_cache() -> None:
    """Clear cached queries so newly committed PostgreSQL data becomes visible."""
    load_stock_news.clear()
    load_statement_trends.clear()
    load_saved_analysis_for_rows.clear()


refresh_postgresql_cache()

st.title("Investing Workbench")

with st.sidebar:
    configured_countries = list(PipelineSettings.from_env().countries)
    country_options = list(dict.fromkeys([
        *DEFAULT_MARKET_COUNTRIES, *configured_countries
    ]))
    countries = st.multiselect(
        "Countries",
        options=country_options,
        default=[country for country in configured_countries if country in country_options],
        format_func=lambda country: country.title(),
        help="Checked countries are included in universe discovery and filtering.",
    )
    universe_source = "index"
    st.caption("Universe: all Norwegian stocks; major national indexes elsewhere; plus US/Canadian REITs and dividend aristocrats.")
    data_source = st.selectbox("Market data", ["auto", "yahoo", "investing"], index=0)
    st.caption("Auto queries both providers, prefers Yahoo values, and fills gaps from Investing.com.")
    days = st.number_input("History days", min_value=30, max_value=3650, value=365, step=30)
    min_score = st.number_input("Min score", min_value=-1.0, max_value=1.0, value=0.01, step=0.01, format="%.2f")
    max_volatility_percent = st.number_input(
        "Max volatility %",
        min_value=0.0,
        max_value=100.0,
        value=6.0,
        step=1.0,
        format="%.2f",
    )
    max_volatility = max_volatility_percent / 100
    min_correlation = st.slider("Cluster correlation", min_value=-1.0, max_value=1.0, value=0.65, step=0.05)

    if st.button("Refresh Universe", width="stretch"):
        with st.spinner("Refreshing stock universe"):
            settings = replace(
                PipelineSettings.from_env(),
                countries=tuple(countries),
                universe_source=universe_source,
            )
            refresh_result = pipeline_refresh_stock_universe(settings)
        st.success(f"Saved {refresh_result['rows']} rows")

if not countries:
    st.warning("Select at least one country in the sidebar.")
    st.stop()

base_universe = query_stock_universe(countries=countries)
if base_universe.empty:
    st.warning("No stock universe rows found.")
    st.stop()

market_label_to_value: dict[str, str] = {}
for row in base_universe[["exchange_mic", "market"]].drop_duplicates().itertuples(index=False):
    mic = str(row.exchange_mic or "").strip()
    market = str(row.market or "").strip()
    value = mic or market
    if value:
        market_label_to_value[f"{mic} - {market}" if mic and market else value] = value
with st.sidebar:
    selected_market_labels = st.multiselect(
        "Markets",
        options=sorted(market_label_to_value),
        default=sorted(market_label_to_value),
        help="Checked markets are included. Uncheck a market to exclude it.",
    )
selected_markets = [market_label_to_value[label] for label in selected_market_labels]
if not selected_markets:
    st.warning("Select at least one market in the sidebar.")
    st.stop()
stock_search = st.text_input("Search ticker or company", value="")

universe = query_stock_universe(
    countries=countries,
    markets=selected_markets,
)
universe = filter_universe_by_search(universe, stock_search)
analyze_all = st.checkbox("Use all filtered stocks", value=False)

sector_metadata = load_sector_metadata_for_rows(universe)
sector_options = sorted(
    sector
    for sector in sector_metadata["sector"].dropna().astype(str).unique().tolist()
    if sector and sector != "Unknown"
) if not sector_metadata.empty else []

selection_mode = st.radio("Select by", ["Stocks", "Sectors"], horizontal=True, disabled=analyze_all)
selected_labels: list[str] = []
selected_sectors: list[str] = []

if selection_mode == "Sectors" and not analyze_all:
    if sector_options:
        selected_sectors = st.multiselect("Sectors", sector_options, default=sector_options[:1])
        sector_counts = (
            sector_metadata[sector_metadata["sector"].isin(selected_sectors)]
            .groupby("sector", as_index=False)
            .agg(stocks=("symbol", "count"), last_run_at=("last_run_at", "max"))
            .sort_values("sector")
        )
        if not sector_counts.empty:
            sector_counts["last_run_at"] = sector_counts["last_run_at"].map(format_timestamp)
        if selected_sectors:
            st.dataframe(round_numeric_frame(sector_counts), width="stretch", hide_index=True)
    else:
        st.info("Sector selection uses saved analysis data. Run analysis once, then reload the app or click Load Saved Analysis.")
else:
    labels = [universe_display(row) for _, row in universe.iterrows()]
    selected_labels = st.multiselect("Stocks", labels, default=labels[: min(8, len(labels))], disabled=analyze_all)

if analyze_all:
    active_rows = universe
elif selection_mode == "Sectors":
    active_rows = rows_for_selected_sectors(universe, sector_metadata, selected_sectors)
else:
    active_rows = selected_rows(universe, selected_labels)

summary_a, summary_b, summary_c = st.columns(3)
summary_a.metric("Universe rows", len(base_universe))
summary_b.metric("Filtered rows", len(universe))
summary_c.metric("Selected rows", len(active_rows))

auto_loaded_cache = False
if "analysis_results" not in st.session_state and not active_rows.empty:
    cached_results = load_saved_analysis_for_rows(active_rows)
    if cached_results:
        st.session_state["analysis_results"] = cached_results
        st.session_state["filtered_analysis_results"] = cached_results
        auto_loaded_cache = True

if auto_loaded_cache:
    latest_run = max(
        (pd.to_datetime(result.get("last_run_at")) for result in st.session_state["analysis_results"] if result.get("last_run_at")),
        default=None,
    )
    st.info(f"Loaded saved analysis from PostgreSQL. Latest run: {format_timestamp(latest_run)}")

tab_universe, tab_watchlist, tab_stock_view, tab_analysis, tab_spider, tab_rankings, tab_clusters = st.tabs(
    ["Universe", "Watchlist", "Stock View", "Analysis", "Spider", "Rankings", "Clusters"]
)

with tab_universe:
    columns = ["symbol", "yahoo_symbol", "name", "country", "market", "exchange_mic", "isin", "currency", "source"]
    st.dataframe(round_numeric_frame(universe[columns]), width="stretch", hide_index=True)

with tab_watchlist:
    watchlist_rows = read_watchlist()
    watchlist_frame = pd.DataFrame(watchlist_rows)
    for field in WATCHLIST_FIELDS:
        if field not in watchlist_frame.columns:
            watchlist_frame[field] = ""
    watchlist_frame = watchlist_frame[WATCHLIST_FIELDS]
    st.dataframe(round_numeric_frame(watchlist_frame), width="stretch", hide_index=True)

    note = st.text_input("Note for selected stocks", value="")
    if st.button("Add Selected Stocks To Watchlist", disabled=active_rows.empty):
        added, path = append_watchlist_rows(rows_for_watchlist(active_rows, notes=note))
        st.success(f"Added {added} stocks to {path}")

    with st.form("manual_watchlist_add"):
        manual_symbol = st.text_input("Symbol").strip().upper()
        manual_country = st.text_input("Country", value="norway").strip().lower()
        manual_exchange = st.text_input("Exchange or MIC").strip()
        manual_name = st.text_input("Name").strip()
        manual_notes = st.text_input("Notes").strip()
        submitted = st.form_submit_button("Add Stock")
        if submitted:
            if not manual_symbol:
                st.warning("Symbol is required.")
            else:
                added, path = append_watchlist_rows(
                    [
                        {
                            "symbol": manual_symbol,
                            "country": manual_country,
                            "exchange": manual_exchange,
                            "name": manual_name,
                            "notes": manual_notes,
                        }
                    ]
                )
                st.success(f"Added {added} stock to {path}")

    edited = st.data_editor(watchlist_frame, num_rows="dynamic", width="stretch", hide_index=True)
    if st.button("Save Edited Watchlist"):
        path = write_watchlist(edited.to_dict("records"))
        st.success(f"Saved watchlist to {path}")

    if st.button("Run Watchlist Analysis", type="primary", disabled=watchlist_frame.empty):
        with st.spinner("Analyzing watchlist"):
            st.session_state["analysis_results"] = analyze_watchlist(
                read_watchlist(),
                days=int(days),
                min_score=float(min_score),
                max_volatility=float(max_volatility),
                data_source=data_source,
            )
            saved_history, saved_snapshots = store_analysis_results(
                st.session_state["analysis_results"],
                fallback_source=data_source,
                days=int(days),
                min_score=float(min_score),
                max_volatility=float(max_volatility),
            )
            st.session_state["filtered_analysis_results"] = st.session_state["analysis_results"]
        st.success(f"Saved {saved_snapshots} analysis snapshots and {saved_history} price histories")

with tab_stock_view:
    if not universe.empty:
        stock_rows = universe.drop_duplicates(["symbol", "country"]).copy()
        stock_rows["_stock_view_label"] = stock_rows.apply(
            lambda row: (
                f"{row.get('symbol', '')} | {row.get('country', 'norway')} | "
                f"{row.get('name', '')}"
            ),
            axis=1,
        )
        stock_lookup = {
            str(row["_stock_view_label"]): row
            for row in stock_rows.to_dict("records")
        }
        open_left, open_right = st.columns([4, 1])
        open_label = open_left.selectbox(
            "Open any universe stock",
            sorted(stock_lookup),
            key="stock_view_universe_stock",
        )
        if open_right.button("Open stock", key="stock_view_open_stock"):
            stock_row = stock_lookup[open_label]
            stock_symbol = str(stock_row.get("symbol") or "")
            stock_country = str(stock_row.get("country") or "norway").lower()
            with st.spinner(f"Loading {stock_symbol}"):
                loaded = query_latest_analysis_snapshots(
                    countries=[stock_country],
                    symbols=[stock_symbol],
                )
                if not loaded:
                    loaded = portfolio_module.analyze_stocks(
                        [stock_symbol],
                        country=stock_country,
                        days=int(days),
                        min_score=float(min_score),
                        max_volatility=float(max_volatility),
                        data_source=data_source,
                    )
                    if loaded and not loaded[0].get("error"):
                        loaded[0]["session_only"] = True
                        loaded[0].setdefault("name", stock_row.get("name") or stock_symbol)
                        loaded[0].setdefault("exchange", stock_row.get("exchange") or "")
                        loaded[0]["yahoo_symbol"] = stock_row.get("yahoo_symbol") or ""
                        loaded[0]["universe_market"] = stock_row.get("market") or ""
                        loaded[0]["universe_isin"] = stock_row.get("isin") or ""

            if loaded and loaded[0].get("error"):
                st.error(str(loaded[0]["error"]))
            elif loaded:
                current = st.session_state.get("analysis_results", [])
                loaded_key = (stock_symbol.upper(), stock_country)
                current = [
                    item for item in current
                    if (
                        str(item.get("symbol", "")).upper(),
                        str(item.get("country", "norway")).lower(),
                    ) != loaded_key
                ]
                st.session_state["analysis_results"] = [loaded[0], *current]
                st.success(
                    "Stock loaded. Live results remain in this browser session; "
                    "Dagster continues writing independently."
                )
        st.caption(
            "Cached stocks are read from PostgreSQL. Stocks not yet processed are "
            "analyzed live without writing to the database."
        )

    results = st.session_state.get("analysis_results", [])
    if not results:
        st.info("Choose a universe stock above and click Open stock.")
    else:
        result_by_label = {
            f"{result.get('symbol')} | {result.get('country', 'norway')} | {result.get('name', '')}": result
            for result in results if result.get("symbol")
        }
        selected_label = st.selectbox("Stock", sorted(result_by_label.keys()))
        result = result_by_label[selected_label]
        selected_symbol = str(result.get("symbol"))
        if result.get("error"):
            st.error(result["error"])
        else:
            scorecard = result.get("scorecard", {})
            technical = result.get("technical", {})
            fundamentals = result.get("fundamentals", {})
            country = str(result.get("country") or "norway").lower()
            refresh_left, refresh_right = st.columns([1, 4])
            if refresh_left.button("Refresh selected stock", key="refresh_stock_intelligence"):
                with st.spinner("Fetching news and provider financial statements"):
                    refresh_result = pipeline_refresh_stock_intelligence(
                        selected_symbol,
                        country,
                        yahoo_symbol=str(result.get("yahoo_symbol") or ""),
                        settings=PipelineSettings.from_env(),
                    )
                    pipeline_build_medallion(
                        PipelineSettings.from_env(),
                        select=["+fact_stock_news", "+fact_fundamental_trend"],
                    )
                    load_stock_news.clear()
                    load_statement_trends.clear()
                if refresh_result["errors"]:
                    st.warning("; ".join(refresh_result["errors"]))
                st.success(
                    f"Added {refresh_result['news_rows']} news and "
                    f"{refresh_result['statement_rows']} statement rows."
                )
            refresh_right.caption(
                "The view reads cached Gold data. Refresh fetches only this stock, "
                "then rebuilds the dependent medallion models."
            )

            overview_view, news_view, quarterly_view, annual_view = st.tabs(
                ["Overview", "Latest news", "Quarterly fundamentals", "Annual fundamentals"]
            )
            with overview_view:
                with st.container(border=True):
                    st.markdown("#### Stock snapshot")
                    top_a, top_b, top_c, top_d, top_e = st.columns(5)
                    top_a.metric("Latest close", format_price(scorecard.get("latest_close")))
                    top_b.metric("Score", format_decimal(scorecard.get("score"), digits=1))
                    top_c.metric("Volatility", format_percent(scorecard.get("volatility")))
                    top_d.metric("Price change", format_percent(scorecard.get("price_change")))
                    top_e.metric("Last run", format_timestamp(result.get("last_run_at")) or "n/a")

                data = result.get("data")
                if isinstance(data, pd.DataFrame) and not data.empty:
                    chart_data = data.sort_values("date")[["date", "close", "ma20", "ma50", "ma200"]]
                    with st.container(border=True):
                        st.markdown("#### Price and moving averages")
                        st.line_chart(chart_data.set_index("date"), width="stretch")

                detail_left, detail_right = st.columns(2)
                detail_height = min(
                    560,
                    max(240, 38 + max(len(technical), len(fundamentals), 1) * 35),
                )
                with detail_left:
                    render_detail_panel(
                        "Technical indicators",
                        "Trend, momentum and moving-average signals.",
                        technical,
                        height=detail_height,
                    )
                with detail_right:
                    render_detail_panel(
                        "Fundamental indicators",
                        "Valuation, profitability, growth and dividend measures. "
                        "Large values use K, M, B and T abbreviations.",
                        fundamentals,
                        height=detail_height,
                    )

            with news_view:
                news = load_stock_news(selected_symbol, country)
                if news.empty:
                    st.info("No cached news is available. Use Refresh selected stock.")
                else:
                    for article in news.itertuples(index=False):
                        title = str(article.title or "Untitled article")
                        url = str(article.url or "")
                        st.markdown(f"#### [{title}]({url})" if url else f"#### {title}")
                        st.caption(
                            " | ".join(
                                value for value in [
                                    str(article.publisher or ""),
                                    format_timestamp(article.published_at),
                                    str(article.provider or ""),
                                ] if value
                            )
                        )
                        if article.summary:
                            st.write(str(article.summary))
                        st.divider()

            with quarterly_view:
                render_statement_history(
                    load_statement_trends(
                        selected_symbol,
                        country,
                        "quarterly",
                    ),
                    "Quarterly",
                )

            with annual_view:
                render_statement_history(
                    load_statement_trends(
                        selected_symbol,
                        country,
                        "annual",
                    ),
                    "Annual",
                )

with tab_analysis:
    load_saved = st.button("Load Database Analysis", disabled=active_rows.empty)
    if load_saved:
        cached_results = load_saved_analysis_for_rows(active_rows)
        if cached_results:
            reset_analysis_filter_state()
            st.session_state["analysis_results"] = cached_results
            st.session_state["filtered_analysis_results"] = cached_results
            st.session_state.pop("rankings", None)
            latest_run = max(
                (pd.to_datetime(result.get("last_run_at")) for result in cached_results if result.get("last_run_at")),
                default=None,
            )
            st.success(f"Loaded {len(cached_results)} saved analyses. Latest run: {format_timestamp(latest_run)}")
        else:
            st.warning("No saved analysis found for the selected stocks.")

    interactive_limit = PipelineSettings.from_env().batch_size
    too_many_for_live_analysis = len(active_rows) > interactive_limit
    if too_many_for_live_analysis:
        st.info(
            f"Database-wide analysis uses saved Dagster results. Live Run Analysis is limited "
            f"to {interactive_limit} stocks; the current selection contains {len(active_rows)}."
        )
    run_analysis = st.button(
        "Run Analysis",
        type="primary",
        disabled=active_rows.empty or too_many_for_live_analysis,
    )
    if run_analysis:
        with st.spinner("Fetching prices and fundamentals"):
            st.session_state["analysis_results"] = analyze_universe(
                active_rows,
                days=int(days),
                min_score=float(min_score),
                max_volatility=float(max_volatility),
                data_source=data_source,
            )
            saved_history, saved_snapshots = store_analysis_results(
                st.session_state["analysis_results"],
                fallback_source=data_source,
                days=int(days),
                min_score=float(min_score),
                max_volatility=float(max_volatility),
            )
            st.session_state["filtered_analysis_results"] = st.session_state["analysis_results"]
        st.success(f"Saved {saved_snapshots} analysis snapshots and {saved_history} price histories")

    results = st.session_state.get("analysis_results", [])
    if results:
        frame = scorecard_frame(results)
        with st.expander("Filter analyzed stocks", expanded=True):
            filtered_frame = analysis_filter_controls(frame)

        filtered_results = filter_results_by_frame(results, filtered_frame)
        st.session_state["filtered_analysis_results"] = filtered_results

        st.dataframe(style_numeric_frame(filtered_frame), width="stretch", hide_index=True)

        if filtered_frame.empty or not filtered_results:
            st.warning("No analyzed stocks match the selected filters.")
        else:
            cli_output = format_cli_report(filtered_results, fallback_source=data_source)
            st.subheader("Command Line Output")
            st.code(cli_output, language="text")

            report_path = generate_watchlist_report(filtered_results, "reports/ui_watchlist_report.html")
            html_report = report_path.read_text(encoding="utf-8")
            st.subheader("HTML Report")
            encoded_report = base64.b64encode(html_report.encode("utf-8")).decode("ascii")
            st.iframe(
                f"data:text/html;base64,{encoded_report}",
                height=720,
                width="stretch",
            )

            if st.button("Save Analysis To PostgreSQL"):
                saved_history, saved_snapshots = store_analysis_results(
                    filtered_results,
                    fallback_source=data_source,
                    days=int(days),
                    min_score=float(min_score),
                    max_volatility=float(max_volatility),
                )
                st.success(f"Saved {saved_snapshots} analysis snapshots and {saved_history} price histories")

with tab_spider:
    results = st.session_state.get("filtered_analysis_results")
    if results is None:
        results = st.session_state.get("analysis_results", [])

    if not results:
        st.info("Run analysis first, then use filters to choose stocks for the spider chart.")
    else:
        radar_frame = spider_frame(results)
        if radar_frame.empty:
            st.info("No analyzed stocks are available for the spider chart.")
        else:
            symbols = radar_frame["symbol"].dropna().astype(str).tolist()
            default_symbols = symbols[: min(4, len(symbols))]
            selected_symbols = st.multiselect("Stocks", symbols, default=default_symbols)
            if len(selected_symbols) > 8:
                st.warning("Showing the first 8 selected stocks to keep the chart readable.")
                selected_symbols = selected_symbols[:8]

            if selected_symbols:
                fig = build_spider_chart(radar_frame, selected_symbols)
                st.plotly_chart(fig, width="stretch")
                st.dataframe(
                    round_numeric_frame(radar_frame[radar_frame["symbol"].isin(selected_symbols)]),
                    width="stretch",
                    hide_index=True,
                )

with tab_rankings:
    all_results = st.session_state.get("analysis_results", [])
    filtered_results = st.session_state.get("filtered_analysis_results")
    results = all_results

    if all_results:
        ranking_scopes = {f"All loaded analyses ({len(all_results)})": all_results}
        if filtered_results is not None and filtered_results:
            ranking_scopes[
                f"Analysis-tab filtered results ({len(filtered_results)})"
            ] = filtered_results
        selected_ranking_scope = st.radio(
            "Ranking scope",
            list(ranking_scopes),
            horizontal=True,
            key="ranking_scope",
        )
        results = ranking_scopes[selected_ranking_scope]

    if not results:
        st.info("Load Database Analysis in the Analysis tab, then build rankings.")
    else:
        st.caption(
            "Fundamental scores use sector-specific indicator weights. Missing values score neutrally; "
            "coverage shows how much of the profile had reported data."
        )
        with st.expander("View sector indicator profiles"):
            st.dataframe(sector_profile_frame(), width="stretch", hide_index=True)

        group_options = {
            "Sector": "sector",
            "Correlation cluster": "correlation_cluster",
            "Market": "market",
            "Country": "country",
            "Industry": "industry",
            "Technical direction": "technical_direction",
            "Recommendation": "recommendation",
            "Valuation bucket": "valuation",
            "Dividend bucket": "dividend",
            "Altman Z-score zone": "altman_z_zone",
            "No grouping": "none",
        }
        rank_left, rank_right = st.columns([1, 1])
        selected_group_label = rank_left.selectbox("Group stocks by", list(group_options.keys()))
        technical_weight = rank_right.slider("Technical weight", 0.0, 1.0, 0.35, 0.05)

        if st.button("Build Rankings", type="primary"):
            group_by = group_options[selected_group_label]
            cluster_map: dict[str, str] = {}
            if group_by == "correlation_cluster":
                ranking_universe = rows_from_results(results)
                with st.spinner("Building correlation groups"):
                    cluster_map, cluster_result = build_correlation_groups(
                        ranking_universe,
                        days=int(days),
                        data_source=data_source,
                        min_correlation=float(min_correlation),
                    )
                    st.session_state["cluster_result"] = cluster_result

            rankings = build_rankings(
                results,
                technical_weight=float(technical_weight),
                group_by=group_by,
                cluster_map=cluster_map,
            )
            st.session_state["rankings"] = rankings

        rankings = st.session_state.get("rankings")
        if isinstance(rankings, pd.DataFrame) and not rankings.empty:
            st.subheader("Top 5 stocks by country and sector")
            st.caption(
                "Each stock is ranked by the same combined score used below. "
                "Groups with fewer than five analyzed stocks show every available stock."
            )
            top_five = top_stocks_by_country_sector(rankings, limit=5)
            top_filter_left, top_filter_right = st.columns(2)
            top_country_options = ["All countries"] + sorted(
                top_five["country"].dropna().astype(str).unique().tolist()
            )
            if st.session_state.get("ranking_top_country") not in top_country_options:
                st.session_state["ranking_top_country"] = "All countries"
            selected_top_country = top_filter_left.selectbox(
                "Top-five country",
                top_country_options,
                key="ranking_top_country",
            )
            country_filtered_top = top_five
            if selected_top_country != "All countries":
                country_filtered_top = country_filtered_top[
                    country_filtered_top["country"] == selected_top_country
                ]
            top_sector_options = ["All sectors"] + sorted(
                country_filtered_top["sector"].dropna().astype(str).unique().tolist()
            )
            if st.session_state.get("ranking_top_sector") not in top_sector_options:
                st.session_state["ranking_top_sector"] = "All sectors"
            selected_top_sector = top_filter_right.selectbox(
                "Top-five sector",
                top_sector_options,
                key="ranking_top_sector",
            )
            if selected_top_sector != "All sectors":
                country_filtered_top = country_filtered_top[
                    country_filtered_top["sector"] == selected_top_sector
                ]

            top_columns = [
                "country",
                "sector",
                "country_sector_rank",
                "symbol",
                "name",
                "ranking_score",
                "technical_score",
                "fundamental_score",
                "fundamental_coverage",
                "dividend_yield",
                "dividend_score",
                "primary_indicators",
            ]
            available_top_columns = [
                column for column in top_columns if column in country_filtered_top.columns
            ]
            st.dataframe(
                style_numeric_frame(country_filtered_top[available_top_columns]),
                width="stretch",
                hide_index=True,
            )

            st.subheader("All rankings")
            ranking_columns = [
                "group",
                "group_rank",
                "sector_rank",
                "sector_percentile",
                "symbol",
                "name",
                "ranking_score",
                "technical_score",
                "fundamental_score",
                "fundamental_coverage",
                "dividend_score",
                "dividend_coverage",
                "primary_indicators",
                "direction",
                "pe_ratio",
                "price_to_book",
                "enterprise_to_ebitda",
                "free_cashflow_yield",
                "funds_from_operations_yield",
                "dividend_yield",
                "dividend_years_paid",
                "consecutive_dividend_years",
                "dividend_cagr_5y",
                "altman_z_score",
                "altman_z_zone",
                "volatility",
                "price_change",
                "sector",
                "industry",
            ]
            available_columns = [column for column in ranking_columns if column in rankings.columns]
            st.dataframe(style_numeric_frame(rankings[available_columns]), width="stretch", hide_index=True)

            chart = px.bar(
                rankings.sort_values("ranking_score", ascending=False).head(40),
                x="symbol",
                y="ranking_score",
                color="group",
                hover_data=["name", "technical_score", "fundamental_score", "fundamental_coverage"],
            )
            chart.update_layout(height=520, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(chart, width="stretch")

            summary = (
                rankings.groupby("group", as_index=False)
                .agg(
                    stocks=("symbol", "count"),
                    avg_score=("ranking_score", "mean"),
                    top_score=("ranking_score", "max"),
                )
                .sort_values("avg_score", ascending=False)
            )
            st.dataframe(round_numeric_frame(summary), width="stretch", hide_index=True)

with tab_clusters:
    run_clusters = st.button("Run Clustering", type="primary", disabled=active_rows.empty)
    if run_clusters:
        symbol_list = active_rows["symbol"].dropna().astype(str).tolist()
        country_map = dict(zip(active_rows["symbol"], active_rows["country"]))
        with st.spinner("Building correlation matrix"):
            price_matrix, errors = build_close_price_matrix(
                symbol_list,
                country_by_symbol=country_map,
                days=int(days),
                data_source=data_source,
            )
            correlation = compute_return_correlation(price_matrix)
            clusters = cluster_by_correlation(correlation, min_correlation=float(min_correlation))
            pairs = correlation_pairs(correlation) if not correlation.empty else pd.DataFrame()
        st.session_state["cluster_result"] = {
            "prices": price_matrix,
            "correlation": correlation,
            "clusters": clusters,
            "pairs": pairs,
            "errors": errors,
        }

    cluster_result = st.session_state.get("cluster_result")
    if cluster_result:
        clusters = cluster_result["clusters"]
        correlation = cluster_result["correlation"]
        pairs = cluster_result["pairs"]
        errors = cluster_result["errors"]

        st.dataframe(round_numeric_frame(clusters), width="stretch", hide_index=True)
        if not correlation.empty:
            fig = px.imshow(correlation, color_continuous_scale="RdBu", zmin=-1, zmax=1, aspect="auto")
            fig.update_layout(height=620, margin=dict(l=20, r=20, t=30, b=20))
            st.plotly_chart(fig, width="stretch")
        if not pairs.empty:
            left, right = st.columns(2)
            left.dataframe(round_numeric_frame(pairs.head(20)), width="stretch", hide_index=True)
            right.dataframe(round_numeric_frame(pairs.sort_values("correlation").head(20)), width="stretch", hide_index=True)
        if errors:
            st.dataframe(round_numeric_frame(pd.DataFrame(errors)), width="stretch", hide_index=True)
