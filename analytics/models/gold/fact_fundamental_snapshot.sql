{{ config(materialized='incremental', unique_key=['stock_key', 'snapshot_date'], incremental_strategy='delete+insert') }}

select
    s.stock_key,
    f.snapshot_date,
    f.data_source,
    f.market_cap,
    f.pe_ratio,
    f.eps,
    f.dividend_yield_ratio,
    f.beta,
    f.one_year_change,
    f.shares_outstanding,
    f.revenue,
    f.revenue_growth,
    f.earnings_growth,
    f.return_on_equity,
    f.return_on_assets,
    f.profit_margins,
    f.operating_margins,
    f.gross_margins,
    f.debt_to_equity,
    f.current_ratio,
    f.free_cashflow,
    f.free_cashflow_yield,
    f.price_to_book,
    f.enterprise_to_ebitda,
    f.peg_ratio,
    f.payout_ratio,
    f.funds_from_operations,
    f.funds_from_operations_yield,
    f.altman_z_score,
    f.altman_z_zone,
    f.dividend_years_paid,
    f.consecutive_dividend_years,
    f.dividend_cagr_5y,
    f.latest_dividend_year,
    f.field_sources_json,
    f.provider_payloads_json,
    f.ingested_at
from {{ ref('silver_fundamental_snapshot') }} f
join {{ ref('dim_stock') }} s
  on s.country = f.country and s.symbol = f.ticker
{% if is_incremental() %}
where f.ingested_at >= coalesce((select max(ingested_at) from {{ this }}), timestamp '1900-01-01') - interval '1 day'
{% endif %}
