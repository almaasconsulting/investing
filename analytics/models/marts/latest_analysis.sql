select
    run_timestamp,
    symbol,
    country,
    name,
    exchange,
    yahoo_symbol,
    universe_market,
    data_source,
    days,
    try_cast(json_extract_string(scorecard_json, '$.score') as double) as technical_score,
    try_cast(json_extract_string(scorecard_json, '$.volatility') as double) as volatility,
    try_cast(json_extract_string(scorecard_json, '$.price_change') as double) as price_change,
    try_cast(json_extract_string(scorecard_json, '$.recommended') as boolean) as recommended,
    json_extract_string(technical_json, '$.direction') as direction,
    try_cast(json_extract_string(technical_json, '$.rsi') as double) as rsi,
    json_extract_string(fundamentals_json, '$.sector') as sector,
    json_extract_string(fundamentals_json, '$.industry') as industry,
    try_cast(json_extract_string(fundamentals_json, '$.altman_z_score') as double) as altman_z_score,
    try_cast(json_extract_string(fundamentals_json, '$.dividend_yield') as double) as dividend_yield,
    try_cast(json_extract_string(fundamentals_json, '$.consecutive_dividend_years') as integer)
        as consecutive_dividend_years,
    notes,
    error
from {{ ref('stg_analysis_snapshot') }}
qualify row_number() over (
    partition by symbol, country
    order by run_timestamp desc
) = 1
