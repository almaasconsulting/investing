{{ config(materialized='incremental', unique_key='record_hash', incremental_strategy='delete+insert') }}

select *, current_timestamp as bronze_loaded_at
from {{ source('landing', 'financial_statement_landing') }}
{% if is_incremental() %}
where fetched_at >= coalesce((select max(fetched_at) from {{ this }}), timestamp '1900-01-01') - interval '2 day'
{% endif %}
