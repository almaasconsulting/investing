{{ config(materialized='incremental', unique_key=['country', 'ticker', 'provider', 'statement_type', 'period_type', 'fiscal_period_end', 'line_item', 'currency'], incremental_strategy='delete+insert') }}

with provider_revisions as (
    select
        upper(trim(ticker)) as ticker,
        trim(yahoo_symbol) as yahoo_symbol,
        lower(trim(country)) as country,
        lower(trim(provider)) as provider,
        lower(trim(statement_type)) as statement_type,
        lower(trim(period_type)) as period_type,
        fiscal_period_end,
        lower(trim(line_item)) as line_item,
        line_item_label, value, upper(trim(currency)) as currency,
        reported_at, fetched_at, record_hash, raw_payload_json,
        row_number() over (
            partition by lower(country), upper(ticker), lower(provider), lower(statement_type),
                         lower(period_type), fiscal_period_end, lower(line_item), upper(trim(currency))
            order by fetched_at desc
        ) as provider_revision_rank
    from {{ ref('bronze_financial_statement') }}
    {% if is_incremental() %}
    where fetched_at >= coalesce((select max(fetched_at) from {{ this }}), timestamp '1900-01-01') - interval '7 day'
    {% endif %}
)
select
    ticker, yahoo_symbol, country, provider, statement_type, period_type,
    fiscal_period_end, line_item, line_item_label, value, currency,
    reported_at, fetched_at, record_hash, raw_payload_json
from provider_revisions
where provider_revision_rank = 1 and value is not null
