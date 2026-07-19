select stock_key, snapshot_date, count(*) as row_count
from {{ ref('fact_fundamental_snapshot') }}
group by stock_key, snapshot_date
having count(*) > 1
