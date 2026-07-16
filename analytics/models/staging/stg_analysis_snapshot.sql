select
    run_timestamp,
    upper(symbol) as symbol,
    lower(country) as country,
    name,
    exchange,
    yahoo_symbol,
    universe_market,
    data_source,
    days,
    min_score,
    max_volatility,
    notes,
    scorecard_json,
    technical_json,
    fundamentals_json,
    metrics_json,
    error
from {{ source('raw', 'analysis_snapshot') }}
