select
    accession_no,
    cik,
    form_type,
    filed_at,
    period_end,
    coalesce(year(period_end), year(filed_at)) as fiscal_year,
    source_url,
    checksum,
    size_bytes,
    ingest_run_id,
    status
from {{ source('lake', 'filings') }}
where form_type <> 'INVOICE'
