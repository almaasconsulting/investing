{{ config(materialized='incremental', unique_key=['stock_key', 'article_key'], incremental_strategy='delete+insert') }}

select
    coalesce(s.stock_key, md5(n.country || '|' || n.ticker)) as stock_key,
    md5(n.provider || '|' || n.article_id) as article_key,
    n.ticker,
    n.country,
    n.published_at,
    n.provider,
    n.fetched_at
from {{ ref('silver_news_article') }} n
left join {{ ref('dim_stock') }} s
  on s.country = n.country and s.symbol = n.ticker
