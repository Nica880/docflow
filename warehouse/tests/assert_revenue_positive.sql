-- Revenue reported or extracted must never be negative.
select * from {{ ref('fct_financials') }} where revenue < 0
