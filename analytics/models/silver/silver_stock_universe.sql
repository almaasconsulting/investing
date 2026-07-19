{{ config(materialized='incremental', unique_key=['country', 'symbol'], incremental_strategy='delete+insert') }}

with ranked as (
    select
        upper(trim(symbol)) as symbol,
        trim(yahoo_symbol) as yahoo_symbol,
        trim(name) as name,
        trim(full_name) as full_name,
        lower(trim(country)) as country,
        trim(market) as market,
        trim(exchange) as exchange,
        upper(trim(exchange_mic)) as exchange_mic,
        trim(isin) as isin,
        upper(trim(currency)) as currency,
        source,
        source_url,
        coalesce(is_active, true) as is_active,
        refreshed_at,
        bronze_loaded_at,
        row_number() over (
            partition by lower(country), upper(symbol)
            order by refreshed_at desc nulls last, bronze_loaded_at desc
        ) as row_rank
    from {{ ref('bronze_stock_universe') }}
    {% if is_incremental() %}
    where refreshed_at >= coalesce((select max(refreshed_at) from {{ this }}), timestamp '1900-01-01')
    {% endif %}
)
select
    symbol, yahoo_symbol, name, full_name, country, market, exchange,
    exchange_mic, isin, currency, source, source_url, is_active,
    refreshed_at, bronze_loaded_at
from ranked where row_rank = 1
