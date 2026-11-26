select
    id as extraction_id,
    accession_no,
    schema_name,
    schema_version,
    model,
    prompt_version,
    overall_confidence,
    attempts,
    latency_ms,
    coalesce(run_tag, 'pipeline') as run_tag,
    coalesce(run_tag, 'pipeline') like 'eval:%' as is_eval,
    created_at
from {{ source('lake', 'extractions') }}
