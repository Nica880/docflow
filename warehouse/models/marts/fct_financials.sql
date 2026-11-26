-- Headline financials per company x fiscal year, from two independent sources:
--   llm  = facts extracted from the 10-K text (reviewer corrections applied)
--   xbrl = the company's own machine-readable XBRL facts (reference values)
with llm as (
    select
        f.cik,
        p.accession_no,
        p.fiscal_year,
        max(case when p.field = 'revenue' then p.value_usd end) as revenue,
        max(case when p.field = 'net_income' then p.value_usd end) as net_income,
        max(case when p.field = 'operating_cash_flow' then p.value_usd end) as operating_cash_flow,
        min(p.confidence) as min_confidence,
        bool_or(p.is_reviewed) as is_reviewed,
        max(f.filed_at) as filed_at
    from {{ ref('int_financials_pipeline') }} p
    join {{ ref('stg_filings') }} f using (accession_no)
    group by f.cik, p.accession_no, p.fiscal_year
    qualify row_number() over (partition by f.cik, p.fiscal_year order by max(f.filed_at) desc) = 1
),

xbrl as (
    select
        cik,
        any_value(accession_no) as accession_no,
        fiscal_year,
        max(case when field = 'revenue' then value end) as revenue,
        max(case when field = 'net_income' then value end) as net_income,
        max(case when field = 'operating_cash_flow' then value end) as operating_cash_flow
    from {{ ref('stg_xbrl_facts') }}
    group by cik, fiscal_year
),

unioned as (
    select cik, accession_no, fiscal_year, 'llm' as source, revenue, net_income,
           operating_cash_flow, min_confidence, is_reviewed
    from llm
    union all
    select cik, accession_no, fiscal_year, 'xbrl' as source, revenue, net_income,
           operating_cash_flow, 1.0 as min_confidence, false as is_reviewed
    from xbrl
)

select
    u.cik,
    c.ticker,
    c.company_name,
    c.sector,
    u.accession_no,
    u.fiscal_year,
    u.source,
    u.revenue,
    u.net_income,
    u.operating_cash_flow,
    u.min_confidence,
    u.is_reviewed
from unioned u
join {{ ref('stg_companies') }} c using (cik)
