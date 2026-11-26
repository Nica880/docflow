select id as section_id, accession_no, item, title, char_count, token_estimate, schema_version
from {{ source('lake', 'sections') }}
