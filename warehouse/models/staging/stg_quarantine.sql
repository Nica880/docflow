select id as quarantine_id, accession_no, split_part(stage, ':', 1) as stage, stage as stage_detail, error, created_at
from {{ source('lake', 'quarantine') }}
