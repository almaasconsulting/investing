{{ config(materialized='incremental', unique_key=['country', 'symbol'], incremental_strategy='delete+insert') }}

select
    *,
    current_timestamp as bronze_loaded_at
from {{ source('landing', 'stock_universe') }}
{% if is_incremental() %}
where refreshed_at >= coalesce((select max(refreshed_at) from {{ this }}), timestamp '1900-01-01')
{% endif %}
