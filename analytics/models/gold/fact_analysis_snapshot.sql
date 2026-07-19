{{ config(materialized='incremental', unique_key=['stock_key', 'run_timestamp'], incremental_strategy='delete+insert') }}

select
    s.stock_key,
    a.run_timestamp,
    a.data_source,
    a.days as analysis_days,
    a.min_score,
    a.max_volatility,
    {{ json_number('a.scorecard_json', 'total_score') }} as total_score,
    {{ json_text('a.scorecard_json', 'recommendation') }} as recommendation,
    {{ json_number('a.technical_json', 'latest_close') }} as latest_close,
    {{ json_number('a.technical_json', 'rsi') }} as rsi,
    {{ json_text('a.technical_json', 'direction') }} as direction,
    {{ sanitize_json('a.scorecard_json') }} as scorecard_json,
    {{ sanitize_json('a.technical_json') }} as technical_json,
    {{ sanitize_json('a.fundamentals_json') }} as fundamentals_json,
    {{ sanitize_json('a.metrics_json') }} as metrics_json,
    a.notes,
    a.error
from {{ ref('silver_analysis_snapshot') }} a
join {{ ref('dim_stock') }} s
  on s.country = a.country and s.symbol = a.symbol
{% if is_incremental() %}
where a.run_timestamp > coalesce((select max(run_timestamp) from {{ this }}), timestamp '1900-01-01')
{% endif %}
