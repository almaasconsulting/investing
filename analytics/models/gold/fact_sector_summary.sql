select
    md5(coalesce(s.sector, 'unknown')) as sector_key,
    coalesce(s.sector, 'unknown') as sector_name,
    f.snapshot_date,
    count(*) as stock_count,
    {{ median('f.pe_ratio') }} as median_pe_ratio,
    {{ median('f.dividend_yield_ratio') }} as median_dividend_yield,
    {{ median('f.return_on_equity') }} as median_return_on_equity,
    {{ median('f.debt_to_equity') }} as median_debt_to_equity,
    {{ median('f.altman_z_score') }} as median_altman_z_score
from {{ ref('fact_fundamental_snapshot') }} f
join {{ ref('dim_stock') }} s using (stock_key)
group by md5(coalesce(s.sector, 'unknown')), coalesce(s.sector, 'unknown'), f.snapshot_date
