{{ config(materialized='incremental', unique_key='date_key', incremental_strategy='delete+insert') }}

select distinct
    {{ date_key('date') }} as date_key,
    date,
    {{ date_part_integer('year', 'date') }} as year,
    {{ date_part_integer('quarter', 'date') }} as quarter,
    {{ date_part_integer('month', 'date') }} as month,
    {{ date_name('month', 'date') }} as month_name,
    {{ date_part_integer('week', 'date') }} as week_of_year,
    {{ date_part_integer('day', 'date') }} as day_of_month,
    {{ date_part_integer('dow', 'date') }} as day_of_week,
    {{ date_name('day', 'date') }} as day_name,
    {{ date_part_integer('dow', 'date') }} in (0, 6) as is_weekend
from {{ ref('silver_stock_price_daily') }}
{% if is_incremental() %}
where date > coalesce((select max(date) from {{ this }}), date '1900-01-01')
{% endif %}
