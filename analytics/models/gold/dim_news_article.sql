{{ config(materialized='incremental', unique_key='article_key', incremental_strategy='delete+insert') }}

with ranked as (
    select *, row_number() over (
        partition by provider, article_id order by fetched_at desc
    ) as article_rank
    from {{ ref('silver_news_article') }}
)
select
    md5(provider || '|' || article_id) as article_key,
    article_id,
    provider,
    provider_article_id,
    title,
    publisher,
    summary,
    url,
    content_type,
    published_at,
    fetched_at
from ranked
where article_rank = 1
