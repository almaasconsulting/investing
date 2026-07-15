from __future__ import annotations

import html
from pathlib import Path
from typing import Iterable


def _cell(value: object) -> str:
    return html.escape(str(value)) if value is not None else ""


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _percent(value: object) -> str:
    return f"{_number(value):.2%}"


def _section(title: str, rows: Iterable[tuple[str, object]]) -> str:
    details = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(str(value))}</td></tr>"
        for label, value in rows
        if value is not None and str(value) != "nan"
    )
    return f"<table class='overview'><caption>{html.escape(title)}</caption>{details}</table>"


def generate_watchlist_report(items: list[dict], output_path: str | Path | None = None) -> Path:
    output_file = Path(output_path) if output_path else Path("reports/watchlist_report.html")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for item in items:
        rows.append(
            """
            <tr>
                <td>{symbol}</td>
                <td>{name}</td>
                <td>{country}</td>
                <td>{exchange}</td>
                <td>{recommended}</td>
                <td>{score:.4f}</td>
                <td>{volatility:.4f}</td>
                <td>{price_change}</td>
                <td>{notes}</td>
            </tr>
            """.format(
                symbol=_cell(item.get("symbol", "")),
                name=_cell(item.get("name", "")),
                country=_cell(item.get("country", "")),
                exchange=_cell(item.get("exchange") or item.get("watchlist_exchange", "")),
                recommended=_cell(item.get("scorecard", {}).get("recommended", "")),
                score=_number(item.get("scorecard", {}).get("score")),
                volatility=_number(item.get("scorecard", {}).get("volatility")),
                price_change=_cell(_percent(item.get("scorecard", {}).get("price_change"))),
                notes=_cell(item.get("notes", "")),
            )
        )

    body_rows = "".join(rows)
    sections = []
    for item in items:
        if item.get("error"):
            sections.append(
                f"<section><h2>{_cell(item.get('symbol', 'Unknown'))} - ERROR</h2>"
                f"<p>{_cell(item['error'])}</p></section>"
            )
            continue

        technical = item.get("technical", {})
        fundamentals = item.get("fundamentals", {})
        sections.append(
            f"<section>"
            f"<h2>{_cell(item.get('symbol'))} - {_cell(item.get('name'))}</h2>"
            f"<p><strong>Watchlist note:</strong> {_cell(item.get('notes', ''))}</p>"
            f"<p><strong>Recommendation:</strong> {_cell(item.get('scorecard', {}).get('recommended', ''))}"
            f" - {_cell(item.get('scorecard', {}).get('reason', ''))}</p>"
            f"{_section('Technical Overview', [
                ('Latest close', technical.get('latest_close')),
                ('Trend direction', technical.get('direction')),
                ('Signal', technical.get('signal_summary')),
                ('RSI (14)', technical.get('rsi')),
                ('20-day MA', technical.get('ma20')),
                ('50-day MA', technical.get('ma50')),
                ('200-day MA', technical.get('ma200')),
            ])}"
            f"{_section('Fundamental KPIs', [
                ('Market cap', fundamentals.get('market_cap')),
                ('P/E ratio', fundamentals.get('pe_ratio')),
                ('EPS', fundamentals.get('eps')),
                ('Dividend yield', fundamentals.get('dividend_yield')),
                ('Beta', fundamentals.get('beta')),
                ('Revenue', fundamentals.get('revenue')),
                ('1-year change', fundamentals.get('one_year_change')),
                ('Sector', fundamentals.get('sector')),
                ('Industry', fundamentals.get('industry')),
                ('Revenue growth', fundamentals.get('revenue_growth')),
                ('Earnings growth', fundamentals.get('earnings_growth')),
                ('Return on equity', fundamentals.get('return_on_equity')),
                ('Profit margins', fundamentals.get('profit_margins')),
                ('Debt to equity', fundamentals.get('debt_to_equity')),
                ('Current ratio', fundamentals.get('current_ratio')),
                ('Free cashflow', fundamentals.get('free_cashflow')),
                ('Altman Z-score', fundamentals.get('altman_z_score')),
                ('Altman Z-score zone', fundamentals.get('altman_z_zone')),
            ])}"
            f"</section>"
        )

    html_document = f"""
    <!doctype html>
    <html lang='en'>
    <head>
      <meta charset='utf-8'>
      <title>Watchlist Report</title>
      <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.5; margin: 24px; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
        table.overview {{ max-width: 800px; }}
        caption {{ text-align: left; font-weight: bold; margin-bottom: 8px; }}
        th, td {{ border: 1px solid #ccc; padding: 8px; }}
        th {{ background: #f5f5f5; text-align: left; }}
        section {{ margin-bottom: 32px; }}
        h1, h2, h3 {{ color: #222; }}
      </style>
    </head>
    <body>
      <h1>Watchlist Report</h1>
      <p>Generated watchlist overview with technical signals, direction, and core fundamental KPIs.</p>
      <h2>Watchlist Table</h2>
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Name</th>
            <th>Country</th>
            <th>Exchange</th>
            <th>Recommended</th>
            <th>Score</th>
            <th>Volatility</th>
            <th>Price change</th>
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {body_rows}
        </tbody>
      </table>
      {''.join(sections)}
    </body>
    </html>
    """
    output_file.write_text(html_document, encoding="utf-8")
    return output_file
