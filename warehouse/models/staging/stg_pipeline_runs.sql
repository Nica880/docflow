select
    run_id,
    dag_id,
    started_at,
    finished_at,
    date_diff('second', started_at, finished_at) as duration_s,
    docs_in,
    docs_ok,
    docs_quarantined,
    status
from {{ source('lake', 'pipeline_runs') }}
