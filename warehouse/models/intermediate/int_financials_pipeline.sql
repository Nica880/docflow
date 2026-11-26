-- Latest pipeline extraction per filing, with reviewer decisions applied:
-- corrected -> reviewer value (entered in the reported units), rejected -> null.
with latest as (
    select e.extraction_id, e.accession_no
    from {{ ref('stg_extractions') }} e
    where e.schema_name = 'FinancialHighlights' and not e.is_eval
    qualify row_number() over (partition by e.accession_no order by e.created_at desc) = 1
),

facts as (
    select f.*
    from {{ ref('stg_financial_facts') }} f
    join latest l using (extraction_id)
),

reviews as (
    select extraction_id, field, status, try_cast(replace(reviewer_value, ',', '') as double) as reviewer_num
    from {{ ref('stg_review_tasks') }}
    where status in ('corrected', 'rejected', 'approved')
)

select
    f.extraction_id,
    f.accession_no,
    f.fiscal_year,
    f.field,
    case
        when r.status = 'rejected' then null
        when r.status = 'corrected' then r.reviewer_num * case f.units
            when 'billions' then 1e9 when 'millions' then 1e6 when 'thousands' then 1e3 else 1 end
        else f.value_usd
    end as value_usd,
    f.confidence,
    r.status is not null as is_reviewed
from facts f
left join reviews r on r.extraction_id = f.extraction_id and r.field = f.field
