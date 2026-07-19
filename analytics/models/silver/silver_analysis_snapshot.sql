{{ config(materialized='incremental', unique_key=['country', 'symbol', 'run_timestamp'], incremental_strategy='delete+insert') }}

select
    run_timestamp,
    upper(trim(symbol)) as symbol,
    lower(trim(country)) as country,
    trim(name) as name,
    trim(exchange) as exchange,
    trim(yahoo_symbol) as yahoo_symbol,
    trim(universe_market) as universe_market,
    trim(universe_isin) as universe_isin,
    data_source,
    days,
    min_score,
    max_volatility,
    notes,
    scorecard_json,
    technical_json,
    fundamentals_json,
    metrics_json,
    nullif(trim(error), '') as error
from {{ ref('bronze_analysis_snapshot') }}
{% if is_incremental() %}
where run_timestamp > coalesce((select max(run_timestamp) from {{ this }}), timestamp '1900-01-01')
{% endif %}
