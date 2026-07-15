from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from investing.core.portfolio import analyze_stocks

DEFAULT_WATCHLIST_PATH = Path(__file__).resolve().parents[2] / "watchlist.csv"
WATCHLIST_FIELDS = ["symbol", "country", "exchange", "name", "notes"]


def _clean_field(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def read_watchlist(path: str | Path | None = None) -> list[dict]:
    file_path = Path(path) if path else DEFAULT_WATCHLIST_PATH
    if not file_path.exists():
        return []

    with file_path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        rows = [
            {key.strip(): (value.strip() if value is not None else "") for key, value in row.items()}
            for row in reader
            if any((value or "").strip() for value in row.values())
        ]
    return rows


def write_watchlist(rows: Iterable[dict], path: str | Path | None = None) -> Path:
    file_path = Path(path) if path else DEFAULT_WATCHLIST_PATH
    file_path.parent.mkdir(parents=True, exist_ok=True)

    normalized_rows = [
        {field: _clean_field(row.get(field, "")) for field in WATCHLIST_FIELDS}
        for row in rows
        if _clean_field(row.get("symbol", ""))
    ]
    with file_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=WATCHLIST_FIELDS)
        writer.writeheader()
        writer.writerows(normalized_rows)
    return file_path


def append_watchlist_rows(rows: Iterable[dict], path: str | Path | None = None) -> tuple[int, Path]:
    file_path = Path(path) if path else DEFAULT_WATCHLIST_PATH
    existing_rows = read_watchlist(file_path) if file_path.exists() else []
    existing_keys = {
        (
            row.get("symbol", "").strip().upper(),
            row.get("country", "").strip().lower(),
        )
        for row in existing_rows
    }

    added = 0
    merged_rows = list(existing_rows)
    for row in rows:
        symbol = _clean_field(row.get("symbol", "")).upper()
        country = (_clean_field(row.get("country", "norway")) or "norway").lower()
        if not symbol:
            continue
        key = (symbol, country)
        if key in existing_keys:
            continue
        existing_keys.add(key)
        merged_rows.append(
            {
                "symbol": symbol,
                "country": country,
                "exchange": _clean_field(row.get("exchange", "")),
                "name": _clean_field(row.get("name", "")),
                "notes": _clean_field(row.get("notes", "")),
            }
        )
        added += 1

    write_watchlist(merged_rows, file_path)
    return added, file_path


def analyze_watchlist(
    rows: Iterable[dict],
    days: int = 180,
    min_score: float = 0.01,
    max_volatility: float = 0.06,
    data_source: str = "auto",
) -> list[dict]:
    symbols: list[str] = []
    countries: list[str] = []
    row_metadata: list[dict] = []

    for row in rows:
        symbol = _clean_field(row.get("symbol", ""))
        if not symbol:
            continue
        country = _clean_field(row.get("country", "norway")) or "norway"
        symbols.append(symbol)
        countries.append(country)
        row_metadata.append({
            "symbol": symbol,
            "country": country,
            "exchange": _clean_field(row.get("exchange", "")),
            "notes": _clean_field(row.get("notes", "")),
        })

    results = []
    for meta in row_metadata:
        analyzed = analyze_stocks(
            [meta["symbol"]],
            country=meta["country"],
            days=days,
            min_score=min_score,
            max_volatility=max_volatility,
            data_source=data_source,
        )
        if analyzed:
            result = analyzed[0]
            result["notes"] = meta["notes"]
            result["watchlist_exchange"] = meta["exchange"]
            results.append(result)

    return results
