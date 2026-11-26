select
    c.cik,
    c.company_name as name,
    c.ticker,
    c.sic_code,
    c.sector,
    count(f.accession_no) as n_filings,
    min(f.filed_at) as first_filed_at,
    max(f.filed_at) as last_filed_at
from {{ ref('stg_companies') }} c
left join {{ ref('stg_filings') }} f using (cik)
group by all
