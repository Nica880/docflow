-- Data-quality / pipeline health report (one row per DAG).
select
    dag_id,
    count(*) as runs,
    count_if(status = 'success') as successful_runs,
    sum(docs_in) as docs_in,
    sum(docs_ok) as docs_ok,
    sum(docs_quarantined) as docs_quarantined,
    round(sum(docs_quarantined)::double / nullif(sum(docs_in), 0), 4) as quarantine_rate,
    round(sum(docs_ok) * 3600.0 / nullif(sum(duration_s), 0), 1) as docs_per_hour,
    max(finished_at) as last_finished_at
from {{ ref('stg_pipeline_runs') }}
group by dag_id
