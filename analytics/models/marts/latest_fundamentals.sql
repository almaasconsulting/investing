select *
from {{ ref('stg_fundamental_snapshot') }}
qualify row_number() over (
    partition by ticker, country
    order by snapshot_date desc
) = 1
