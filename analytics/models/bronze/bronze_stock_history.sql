{{ config(materialized='incremental', unique_key=['country', 'ticker', 'date', 'ingested_at'], incremental_strategy='delete+insert') }}

select
    *,
    current_timestamp as bronze_loaded_at
from {{ source('landing', 'stock_history') }}
{% if is_incremental() %}
where ingested_at > coalesce((select max(ingested_at) from {{ this }}), timestamp '1900-01-01')
{% endif %}
