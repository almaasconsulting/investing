{{ config(materialized='incremental', unique_key=['country', 'symbol', 'run_timestamp'], incremental_strategy='delete+insert') }}

select
    *,
    current_timestamp as bronze_loaded_at
from {{ source('landing', 'analysis_snapshot') }}
{% if is_incremental() %}
where run_timestamp > coalesce((select max(run_timestamp) from {{ this }}), timestamp '1900-01-01')
{% endif %}
