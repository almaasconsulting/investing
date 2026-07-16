select ticker, country, count(*) as records
from {{ ref('latest_fundamentals') }}
group by ticker, country
having count(*) > 1
