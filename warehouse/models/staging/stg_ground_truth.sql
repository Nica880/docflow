select accession_no, field, try_cast(value as double) as value_num, value, source
from {{ source('lake', 'ground_truth') }}
