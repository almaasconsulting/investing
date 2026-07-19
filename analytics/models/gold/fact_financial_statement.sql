{{ config(materialized='incremental', unique_key=['country', 'ticker', 'statement_type', 'period_type', 'fiscal_period_end', 'line_item', 'currency'], incremental_strategy='delete+insert') }}

with candidates as (
    select
        s.*,
        count(*) over (
            partition by country, ticker, statement_type, period_type,
                         fiscal_period_end, line_item, currency
        ) as available_provider_count,
        row_number() over (
            partition by country, ticker, statement_type, period_type,
                         fiscal_period_end, line_item, currency
            order by case provider when 'yahoo' then 1 when 'investing' then 2 else 9 end,
                     fetched_at desc
        ) as provider_rank
    from {{ ref('silver_financial_statement') }} s
)
select
    coalesce(d.stock_key, md5(c.country || '|' || c.ticker)) as stock_key,
    c.ticker,
    c.country,
    c.yahoo_symbol,
    c.statement_type,
    c.period_type,
    c.fiscal_period_end,
    c.line_item,
    c.line_item_label,
    c.value,
    c.currency,
    c.provider as selected_source,
    c.available_provider_count,
    c.reported_at,
    c.fetched_at,
    c.record_hash
from candidates c
left join {{ ref('dim_stock') }} d
  on d.country = c.country and d.symbol = c.ticker
where c.provider_rank = 1
{% if is_incremental() %}
  and c.fetched_at >= coalesce((select max(fetched_at) from {{ this }}), timestamp '1900-01-01') - interval '7 day'
{% endif %}
