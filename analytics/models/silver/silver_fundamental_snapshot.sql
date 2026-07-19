{{ config(materialized='incremental', unique_key=['country', 'ticker', 'snapshot_date'], incremental_strategy='delete+insert') }}

with ranked as (
    select
        snapshot_date, upper(trim(ticker)) as ticker, trim(name) as name,
        lower(trim(country)) as country, trim(exchange) as exchange, data_source,
        market_cap, pe_ratio, eps, dividend_yield,
        {{ normalized_percent("coalesce(dividend_yield, '')") }} as dividend_yield_ratio,
        beta, one_year_change, shares_outstanding, revenue, prev_close,
        lower(trim(sector)) as sector, lower(trim(industry)) as industry,
        revenue_growth, earnings_growth, return_on_equity, profit_margins,
        debt_to_equity, current_ratio, free_cashflow, altman_z_score,
        altman_z_zone, return_on_assets, operating_margins, gross_margins,
        free_cashflow_yield, price_to_book, enterprise_to_ebitda, peg_ratio,
        payout_ratio, funds_from_operations, funds_from_operations_yield,
        dividend_years_paid, consecutive_dividend_years, dividend_cagr_5y,
        latest_dividend_year, field_sources_json, provider_payloads_json,
        record_hash, ingested_at,
        row_number() over (
            partition by lower(country), upper(ticker), snapshot_date
            order by ingested_at desc nulls last
        ) as row_rank
    from {{ ref('bronze_fundamental_snapshot') }}
    {% if is_incremental() %}
    where ingested_at >= coalesce((select max(ingested_at) from {{ this }}), timestamp '1900-01-01') - interval '1 day'
    {% endif %}
)
select
    snapshot_date, ticker, name, country, exchange, data_source, market_cap,
    pe_ratio, eps, dividend_yield, dividend_yield_ratio, beta, one_year_change,
    shares_outstanding, revenue, prev_close, sector, industry, revenue_growth,
    earnings_growth, return_on_equity, profit_margins, debt_to_equity,
    current_ratio, free_cashflow, altman_z_score, altman_z_zone,
    return_on_assets, operating_margins, gross_margins, free_cashflow_yield,
    price_to_book, enterprise_to_ebitda, peg_ratio, payout_ratio,
    funds_from_operations, funds_from_operations_yield, dividend_years_paid,
    consecutive_dividend_years, dividend_cagr_5y, latest_dividend_year,
    field_sources_json, provider_payloads_json, record_hash, ingested_at
from ranked where row_rank = 1
