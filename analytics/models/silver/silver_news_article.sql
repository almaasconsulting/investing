{{ config(materialized='incremental', unique_key=['country', 'ticker', 'article_id'], incremental_strategy='delete+insert') }}

with ranked as (
    select
        article_id, provider_article_id,
        upper(trim(ticker)) as ticker,
        trim(yahoo_symbol) as yahoo_symbol,
        lower(trim(country)) as country,
        lower(trim(provider)) as provider,
        published_at, trim(title) as title, publisher, summary,
        trim(url) as url, content_type, raw_payload_json, fetched_at, record_hash,
        row_number() over (
            partition by lower(country), upper(ticker), article_id
            order by fetched_at desc
        ) as row_rank
    from {{ ref('bronze_news_article') }}
    {% if is_incremental() %}
    where fetched_at >= coalesce((select max(fetched_at) from {{ this }}), timestamp '1900-01-01') - interval '2 day'
    {% endif %}
)
select
    article_id, provider_article_id, ticker, yahoo_symbol, country, provider,
    published_at, title, publisher, summary, url, content_type,
    raw_payload_json, fetched_at, record_hash
from ranked
where row_rank = 1 and (title <> '' or url <> '')
