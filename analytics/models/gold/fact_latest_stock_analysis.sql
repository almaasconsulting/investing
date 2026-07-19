select
    stock_key, run_timestamp, data_source, analysis_days, min_score,
    max_volatility, total_score, recommendation, latest_close, rsi,
    direction, scorecard_json, technical_json, fundamentals_json,
    metrics_json, notes, error
from (
    select
        *,
        row_number() over (
            partition by stock_key order by run_timestamp desc
        ) as analysis_rank
    from {{ ref('fact_analysis_snapshot') }}
)
where analysis_rank = 1
