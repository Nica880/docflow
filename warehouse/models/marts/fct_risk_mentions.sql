with latest as (
    select extraction_id, accession_no
    from {{ ref('stg_extractions') }}
    where schema_name = 'RiskFactors' and not is_eval
    qualify row_number() over (partition by accession_no order by created_at desc) = 1
)

select
    f.cik,
    c.ticker,
    c.company_name,
    c.sector,
    r.accession_no,
    f.fiscal_year,
    r.category,
    count(*) as mentions,
    avg(r.confidence) as avg_confidence
from {{ ref('stg_risk_mentions') }} r
join latest l using (extraction_id)
join {{ ref('stg_filings') }} f on f.accession_no = r.accession_no
join {{ ref('stg_companies') }} c on c.cik = f.cik
group by all
