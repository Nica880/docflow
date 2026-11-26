select
    f.accession_no,
    f.cik,
    f.form_type,
    f.filed_at,
    f.period_end,
    f.fiscal_year,
    f.status,
    f.size_bytes,
    count(s.section_id) as n_sections,
    coalesce(sum(s.char_count), 0) as total_chars
from {{ ref('stg_filings') }} f
left join {{ ref('stg_sections') }} s using (accession_no)
group by all
