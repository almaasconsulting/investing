select stock_key, date_key, count(*) as row_count
from {{ ref('fact_stock_price_daily') }}
group by stock_key, date_key
having count(*) > 1
