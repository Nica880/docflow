{{ config(severity='warn') }}
-- An extracted fiscal year must be within one year of the filing's period end.
select p.accession_no, p.fiscal_year, f.fiscal_year as filing_year
from {{ ref('int_financials_pipeline') }} p
join {{ ref('stg_filings') }} f using (accession_no)
where abs(p.fiscal_year - f.fiscal_year) > 1
