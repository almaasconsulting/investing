{{ config(materialized='incremental', unique_key=['country', 'ticker', 'date'], incremental_strategy='delete+insert') }}

with ranked as (
    select
        cast(date as date) as date,
        upper(trim(ticker)) as ticker,
        trim(name) as name,
        lower(trim(country)) as country,
        trim(exchange) as exchange,
        data_source,
        price_source,
        cast(open as double precision) as open,
        cast(high as double precision) as high,
        cast(low as double precision) as low,
        cast(close as double precision) as close,
        cast(volume as bigint) as volume,
        cast(yahoo_open as double precision) as yahoo_open,
        cast(yahoo_high as double precision) as yahoo_high,
        cast(yahoo_low as double precision) as yahoo_low,
        cast(yahoo_close as double precision) as yahoo_close,
        cast(yahoo_volume as double precision) as yahoo_volume,
        cast(investing_open as double precision) as investing_open,
        cast(investing_high as double precision) as investing_high,
        cast(investing_low as double precision) as investing_low,
        cast(investing_close as double precision) as investing_close,
        cast(investing_volume as double precision) as investing_volume,
        cast(ma20 as double precision) as ma20,
        cast(ma50 as double precision) as ma50,
        cast(ma200 as double precision) as ma200,
        cast(rsi14 as double precision) as rsi14,
        direction,
        signal_summary,
        ingested_at,
        row_number() over (
            partition by lower(country), upper(ticker), date
            order by ingested_at desc nulls last
        ) as row_rank
    from {{ ref('bronze_stock_history') }}
    {% if is_incremental() %}
    where ingested_at >= coalesce((select max(ingested_at) from {{ this }}), timestamp '1900-01-01') - interval '1 day'
    {% endif %}
)
select
    date, ticker, name, country, exchange, data_source, price_source,
    open, high, low, close, volume,
    yahoo_open, yahoo_high, yahoo_low, yahoo_close, yahoo_volume,
    investing_open, investing_high, investing_low, investing_close, investing_volume,
    ma20, ma50, ma200, rsi14, direction, signal_summary, ingested_at
from ranked where row_rank = 1
