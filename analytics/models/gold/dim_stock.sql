{{ config(materialized='incremental', unique_key='stock_key', incremental_strategy='delete+insert') }}

with latest_fundamentals as (
    select country, ticker, sector, industry
    from (
        select country, ticker, sector, industry,
               row_number() over (
                   partition by country, ticker
                   order by snapshot_date desc, ingested_at desc
               ) as fundamental_rank
        from {{ ref('silver_fundamental_snapshot') }}
    ) ranked_fundamentals
    where fundamental_rank = 1
), stocks as (
    select
        md5(u.country || '|' || u.symbol) as stock_key,
        u.symbol,
        u.yahoo_symbol,
        u.name,
        u.full_name,
        u.country,
        u.market,
        u.exchange,
        u.exchange_mic,
        u.isin,
        u.currency,
        coalesce(f.sector, 'unknown') as sector,
        coalesce(f.industry, 'unknown') as industry,
        u.is_active,
        u.refreshed_at
    from {{ ref('silver_stock_universe') }} u
    left join latest_fundamentals f
      on f.country = u.country and f.ticker = u.symbol
)
select * from stocks
{% if is_incremental() %}
where refreshed_at >= coalesce((select max(refreshed_at) from {{ this }}), timestamp '1900-01-01')
{% endif %}
