select
    md5(coalesce(sector, 'unknown')) as sector_key,
    coalesce(sector, 'unknown') as sector_name
from {{ ref('dim_stock') }}
group by md5(coalesce(sector, 'unknown')), coalesce(sector, 'unknown')
