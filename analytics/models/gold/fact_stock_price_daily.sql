{{ config(materialized='incremental', unique_key=['stock_key', 'date_key'], incremental_strategy='delete+insert') }}

select
    s.stock_key,
    {{ date_key('p.date') }} as date_key,
    p.date,
    p.open,
    p.high,
    p.low,
    p.close,
    p.volume,
    p.ma20,
    p.ma50,
    p.ma200,
    p.rsi14,
    p.direction,
    p.signal_summary,
    p.data_source,
    p.price_source,
    p.yahoo_open,
    p.yahoo_high,
    p.yahoo_low,
    p.yahoo_close,
    p.yahoo_volume,
    p.investing_open,
    p.investing_high,
    p.investing_low,
    p.investing_close,
    p.investing_volume,
    p.ingested_at
from {{ ref('silver_stock_price_daily') }} p
join {{ ref('dim_stock') }} s
  on s.country = p.country and s.symbol = p.ticker
{% if is_incremental() %}
where p.ingested_at >= coalesce((select max(ingested_at) from {{ this }}), timestamp '1900-01-01') - interval '1 day'
{% endif %}
