select
    extraction_id,
    accession_no,
    risk_index,
    category,
    summary,
    snippet,
    confidence,
    model,
    prompt_version,
    coalesce(run_tag, 'pipeline') as run_tag
from {{ source('lake', 'risk_mentions') }}
