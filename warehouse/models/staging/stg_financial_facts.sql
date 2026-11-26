select
    extraction_id,
    accession_no,
    fiscal_year,
    field,
    value,
    units,
    value_usd,
    snippet,
    confidence,
    model,
    prompt_version,
    coalesce(run_tag, 'pipeline') as run_tag
from {{ source('lake', 'financial_facts') }}
