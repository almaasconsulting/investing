select
    coalesce(sector, 'Unknown') as sector,
    count(*) as stocks,
    avg(pe_ratio) as average_pe_ratio,
    avg(dividend_yield) as average_dividend_yield,
    avg(return_on_equity) as average_return_on_equity,
    avg(revenue_growth) as average_revenue_growth,
    avg(free_cashflow_yield) as average_free_cashflow_yield,
    avg(altman_z_score) as average_altman_z_score,
    avg(consecutive_dividend_years) as average_consecutive_dividend_years,
    max(snapshot_date) as latest_snapshot_date
from {{ ref('latest_fundamentals') }}
group by 1
