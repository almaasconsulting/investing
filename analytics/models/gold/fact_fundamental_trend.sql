{{ config(materialized='table') }}

with changes as (
    select
        *,
        lag(value, 1) over metric_window as previous_period_value,
        case when period_type = 'quarterly'
             then lag(value, 4) over metric_window
             else lag(value, 1) over metric_window
        end as previous_year_value
    from {{ ref('fact_financial_statement') }}
    window metric_window as (
        partition by country, ticker, statement_type, period_type, line_item, currency
        order by fiscal_period_end
    )
)
select
    *,
    case when previous_period_value is null or previous_period_value = 0 then null
         else (value - previous_period_value) / abs(previous_period_value) end as period_change_ratio,
    case when previous_year_value is null or previous_year_value = 0 then null
         else (value - previous_year_value) / abs(previous_year_value) end as year_over_year_change_ratio
from changes
