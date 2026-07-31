from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from investing.core.cluster_optimizer import optimize_stock_clusters
from investing.core.cluster_report import generate_cluster_report
from investing.core.clustering import build_close_price_matrix
from investing.core.ranking import parse_number
from investing.db.store import (
    query_latest_analysis_snapshots,
    query_stock_history_coverage,
    query_stock_universe,
)


FUNDAMENTAL_FIELDS = (
    "market_cap",
    "pe_ratio",
    "price_to_book",
    "return_on_equity",
    "profit_margins",
    "revenue_growth",
    "earnings_growth",
    "debt_to_equity",
    "current_ratio",
    "dividend_yield",
)


def _json_value(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def _metadata_from_snapshots(
    snapshots: list[dict],
    universe: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for snapshot in snapshots:
        fundamentals = snapshot.get("fundamentals") or {}
        dividend_yield = parse_number(fundamentals.get("dividend_yield"))
        dividend_years = parse_number(fundamentals.get("dividend_years_paid"))
        row = {
            "symbol": str(snapshot.get("symbol") or "").strip(),
            "sector": fundamentals.get("sector"),
            "industry": fundamentals.get("industry"),
            "dividend_payer": (
                1.0
                if (dividend_yield or 0.0) > 0 or (dividend_years or 0.0) > 0
                else 0.0
            ),
        }
        row.update(
            {
                field: parse_number(fundamentals.get(field))
                for field in FUNDAMENTAL_FIELDS
            }
        )
        rows.append(row)

    identity_columns = [
        column
        for column in ("symbol", "country", "name", "full_name", "market", "exchange")
        if column in universe.columns
    ]
    identities = universe[identity_columns].drop_duplicates("symbol")
    metadata = pd.DataFrame(rows)
    if metadata.empty:
        return identities
    return identities.merge(
        metadata.drop_duplicates("symbol", keep="first"),
        on="symbol",
        how="left",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Tune stock clustering against price and fundamental data already "
            "stored in PostgreSQL. This command does not fetch market data."
        )
    )
    parser.add_argument("--days", type=int, default=730)
    parser.add_argument("--max-stocks", type=int, default=100)
    parser.add_argument("--min-observations", type=int, default=120)
    parser.add_argument(
        "--countries",
        default="",
        help="Optional comma-separated country filter, for example norway,sweden.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/cluster_tuning.json"),
    )
    parser.add_argument(
        "--html-output",
        type=Path,
        default=Path("reports/cluster_tuning.html"),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.days < 60:
        raise SystemExit("--days must be at least 60")
    if args.max_stocks < 4:
        raise SystemExit("--max-stocks must be at least 4")
    if args.min_observations < 45:
        raise SystemExit("--min-observations must be at least 45")

    countries = [
        value.strip()
        for value in args.countries.split(",")
        if value.strip()
    ]
    universe = query_stock_universe(
        countries=countries or None,
        active_only=True,
    )
    if universe.empty:
        raise SystemExit("No active stocks were found in the database.")

    universe = universe.copy()
    universe["symbol"] = universe["symbol"].astype(str).str.strip()
    universe = universe[universe["symbol"] != ""].drop_duplicates(
        "symbol",
        keep="first",
    )
    requested_stocks = list(
        universe[["symbol", "country"]].itertuples(index=False, name=None)
    )
    coverage = query_stock_history_coverage(
        requested_stocks,
        days=args.days,
    )
    eligible = coverage[
        pd.to_numeric(
            coverage["observation_count"],
            errors="coerce",
        ).fillna(0) >= args.min_observations
    ].head(args.max_stocks)
    eligible_symbols = eligible["symbol"].astype(str).tolist()
    eligible_countries = eligible.set_index("symbol")["country"].to_dict()
    if len(eligible_symbols) < 4:
        raise SystemExit(
            "Fewer than four stocks have enough stored price observations. "
            "Run the database update jobs or lower --min-observations."
        )

    prices, price_errors = build_close_price_matrix(
        eligible_symbols,
        eligible_countries,
        days=args.days,
    )
    available_symbols = [
        symbol for symbol in eligible_symbols if symbol in prices.columns
    ]
    prices = prices[available_symbols].sort_index()
    if prices.shape[1] < 4:
        raise SystemExit(
            "Fewer than four selected stocks returned stored price rows."
        )
    selected_universe = universe[
        universe["symbol"].isin(eligible_symbols)
    ].copy()
    snapshots = query_latest_analysis_snapshots(
        countries=countries or None,
        symbols=eligible_symbols,
        include_history=False,
    )
    metadata = _metadata_from_snapshots(snapshots, selected_universe)
    result = optimize_stock_clusters(prices, metadata)

    identity_columns = [
        column
        for column in ("symbol", "name", "full_name", "country", "market")
        if column in metadata.columns
    ]
    cluster_rows = result["clusters"].merge(
        metadata[identity_columns].drop_duplicates("symbol"),
        on="symbol",
        how="left",
    )
    top_trials = result["trials"].head(25)
    settings = {
        "days": args.days,
        "max_stocks": args.max_stocks,
        "min_observations": args.min_observations,
        "countries": countries,
    }
    data_summary = {
        "universe_stocks": len(universe),
        "eligible_stocks": prices.shape[1],
        "price_dates": len(prices),
        "first_price_date": _json_value(prices.index.min()),
        "last_price_date": _json_value(prices.index.max()),
        "fundamental_snapshots": len(snapshots),
        "missing_price_histories": len(price_errors),
        "training_dates": result["train_dates"],
        "validation_dates": result["validation_dates"],
        "validation_start": _json_value(result["split_date"]),
    }
    html_output = generate_cluster_report(
        result,
        metadata,
        data_summary,
        settings,
        args.html_output.resolve(),
    )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_source": "PostgreSQL only; no external data was fetched",
        "html_report": str(html_output),
        "settings": settings,
        "data_summary": data_summary,
        "best_parameters": {
            key: _json_value(value)
            for key, value in result["best"].items()
        },
        "top_trials": [
            {key: _json_value(value) for key, value in row.items()}
            for row in top_trials.to_dict("records")
        ],
        "clusters": [
            {key: _json_value(value) for key, value in row.items()}
            for row in cluster_rows.to_dict("records")
        ],
    }

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    best = report["best_parameters"]
    print(f"Analysed {prices.shape[1]} stocks across {len(prices)} dates.")
    print(
        "Best: "
        f"{best['cluster_count']} clusters, "
        f"linkage={best['linkage']}, "
        f"fundamentals={best['fundamental_weight']:.0%}, "
        f"performance={best['realized_performance_weight']:.0%}, "
        f"co-movement={best['co_movement_weight']:.0%}."
    )
    print(
        "Validation silhouette: "
        f"{best['validation_silhouette']:.3f}; "
        f"objective: {best['objective']:.3f}."
    )
    print(f"Report: {output}")
    print(f"HTML report: {html_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
