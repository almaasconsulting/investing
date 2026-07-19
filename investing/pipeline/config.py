from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from investing.core.watchlist import DEFAULT_WATCHLIST_PATH
from investing.db.store import get_database_url
from investing.data_fetch.stock_universe import DEFAULT_MARKET_COUNTRIES


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    value = os.getenv(name, default)
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class PipelineSettings:
    watchlist_path: Path
    database_path: Path | None = None
    database_url: str = field(default="", repr=False)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_database: str = "investing"
    postgres_user: str = "investing"
    postgres_password: str = field(default="", repr=False)
    postgres_sslmode: str = "prefer"
    postgres_schema: str = "main"
    countries: tuple[str, ...] = DEFAULT_MARKET_COUNTRIES
    universe_source: str = "index"
    data_source: str = "auto"
    analysis_days: int = 1825
    analysis_scope: str = "universe"
    incremental_overlap_days: int = 7
    full_refresh: bool = False
    max_stocks: int | None = None
    content_scope: str = "universe"
    content_max_stocks: int | None = None
    batch_size: int = 200
    batch_partition_count: int = 50
    fetch_workers: int = 4
    news_count: int = 30
    min_score: float = 0.01
    max_volatility: float = 0.06

    @classmethod
    def from_env(cls) -> "PipelineSettings":
        watchlist = Path(
            os.getenv("INVESTING_WATCHLIST_PATH", str(DEFAULT_WATCHLIST_PATH))
        ).expanduser().resolve()
        return cls(
            watchlist_path=watchlist,
            database_url=get_database_url(),
            postgres_host=os.getenv("INVESTING_POSTGRES_HOST", "localhost").strip(),
            postgres_port=int(os.getenv("INVESTING_POSTGRES_PORT", "5432")),
            postgres_database=os.getenv(
                "INVESTING_POSTGRES_DATABASE", "investing"
            ).strip(),
            postgres_user=os.getenv("INVESTING_POSTGRES_USER", "investing").strip(),
            postgres_password=os.getenv("INVESTING_POSTGRES_PASSWORD", ""),
            postgres_sslmode=os.getenv(
                "INVESTING_POSTGRES_SSLMODE", "prefer"
            ).strip(),
            postgres_schema=os.getenv("INVESTING_POSTGRES_SCHEMA", "main").strip(),
            countries=_csv_env(
                "INVESTING_COUNTRIES", ",".join(DEFAULT_MARKET_COUNTRIES)
            ),
            universe_source=os.getenv("INVESTING_UNIVERSE_SOURCE", "index").strip().lower(),
            data_source=os.getenv("INVESTING_DATA_SOURCE", "auto").strip().lower(),
            analysis_days=int(os.getenv("INVESTING_ANALYSIS_DAYS", "1825")),
            analysis_scope=os.getenv("INVESTING_ANALYSIS_SCOPE", "universe").strip().lower(),
            incremental_overlap_days=int(
                os.getenv("INVESTING_INCREMENTAL_OVERLAP_DAYS", "7")
            ),
            full_refresh=os.getenv("INVESTING_FULL_REFRESH", "false").strip().lower()
            in {"1", "true", "yes", "on"},
            max_stocks=(
                int(os.getenv("INVESTING_MAX_STOCKS", ""))
                if os.getenv("INVESTING_MAX_STOCKS", "").strip()
                else None
            ),
            content_scope=os.getenv("INVESTING_CONTENT_SCOPE", "universe").strip().lower(),
            content_max_stocks=(
                int(os.getenv("INVESTING_CONTENT_MAX_STOCKS", ""))
                if os.getenv("INVESTING_CONTENT_MAX_STOCKS", "").strip()
                else None
            ),
            batch_size=max(1, int(os.getenv("INVESTING_BATCH_SIZE", "200"))),
            batch_partition_count=max(
                1, int(os.getenv("INVESTING_BATCH_PARTITION_COUNT", "50"))
            ),
            fetch_workers=min(
                16, max(1, int(os.getenv("INVESTING_FETCH_WORKERS", "4")))
            ),
            news_count=int(os.getenv("INVESTING_NEWS_COUNT", "30")),
            min_score=float(os.getenv("INVESTING_MIN_SCORE", "0.01")),
            max_volatility=float(os.getenv("INVESTING_MAX_VOLATILITY", "0.06")),
        )
