{{ config(materialized='incremental', unique_key=['country', 'ticker', 'article_id'], incremental_strategy='delete+insert') }}

select
    coalesce(s.stock_key, md5(n.country || '|' || n.ticker)) as stock_key,
    n.article_id,
    n.provider_article_id,
    n.ticker,
    n.yahoo_symbol,
    n.country,
    n.provider,
    n.published_at,
    n.title,
    n.publisher,
    n.summary,
    n.url,
    n.content_type,
    n.fetched_at
from {{ ref('silver_news_article') }} n
left join {{ ref('dim_stock') }} s
  on s.country = n.country and s.symbol = n.ticker
{% if is_incremental() %}
where n.fetched_at >= coalesce((select max(fetched_at) from {{ this }}), timestamp '1900-01-01') - interval '2 day'
{% endif %}
