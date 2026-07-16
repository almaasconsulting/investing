from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from investing.core.watchlist import DEFAULT_WATCHLIST_PATH
from investing.db.duckdb_store import get_db_path


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    value = os.getenv(name, default)
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class PipelineSettings:
    database_path: Path
    watchlist_path: Path
    countries: tuple[str, ...] = ("norway",)
    universe_source: str = "auto"
    data_source: str = "auto"
    analysis_days: int = 1825
    min_score: float = 0.01
    max_volatility: float = 0.06
    update_lock_timeout: int = 60

    @property
    def lock_path(self) -> Path:
        return self.database_path.with_suffix(self.database_path.suffix + ".update.lock")

    @classmethod
    def from_env(cls) -> "PipelineSettings":
        watchlist = Path(
            os.getenv("INVESTING_WATCHLIST_PATH", str(DEFAULT_WATCHLIST_PATH))
        ).expanduser().resolve()
        return cls(
            database_path=get_db_path(),
            watchlist_path=watchlist,
            countries=_csv_env("INVESTING_COUNTRIES", "norway"),
            universe_source=os.getenv("INVESTING_UNIVERSE_SOURCE", "auto").strip().lower(),
            data_source=os.getenv("INVESTING_DATA_SOURCE", "auto").strip().lower(),
            analysis_days=int(os.getenv("INVESTING_ANALYSIS_DAYS", "1825")),
            min_score=float(os.getenv("INVESTING_MIN_SCORE", "0.01")),
            max_volatility=float(os.getenv("INVESTING_MAX_VOLATILITY", "0.06")),
            update_lock_timeout=int(os.getenv("INVESTING_UPDATE_LOCK_TIMEOUT", "60")),
        )
