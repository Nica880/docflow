select
    id as review_task_id,
    extraction_id,
    field,
    value,
    confidence,
    status,
    reviewer_value,
    reviewed_at
from {{ source('lake', 'review_tasks') }}
