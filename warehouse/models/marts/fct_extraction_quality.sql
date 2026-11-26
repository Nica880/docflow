-- Extraction quality per model x prompt version x schema (pipeline + eval runs).
with fields as (
    select
        ff.extraction_id,
        ff.field,
        ff.value_usd,
        gt.value_num as truth
    from {{ ref('stg_financial_facts') }} ff
    left join {{ ref('stg_ground_truth') }} gt
        on gt.accession_no = ff.accession_no and gt.field = ff.field and gt.source = 'xbrl'
),

match as (
    select
        extraction_id,
        count(truth) as n_with_truth,
        count_if(truth is not null and value_usd is not null
                 and abs(value_usd - truth) <= 0.005 * abs(truth)) as n_match
    from fields
    group by extraction_id
),

reviews as (
    select extraction_id, count(*) as n_reviews
    from {{ ref('stg_review_tasks') }}
    group by extraction_id
)

select
    e.model,
    e.prompt_version,
    e.schema_name,
    count(*) as n_extractions,
    round(avg(e.overall_confidence), 3) as avg_confidence,
    round(avg(e.latency_ms), 0) as avg_latency_ms,
    round(avg(e.attempts), 2) as avg_attempts,
    round(count_if(coalesce(r.n_reviews, 0) > 0)::double / count(*), 3) as review_rate,
    round(sum(m.n_match)::double / nullif(sum(m.n_with_truth), 0), 3) as xbrl_match_rate
from {{ ref('stg_extractions') }} e
left join reviews r using (extraction_id)
left join match m using (extraction_id)
group by all
