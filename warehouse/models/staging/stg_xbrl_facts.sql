-- One value per company x fiscal year x field: the most recently filed annual fact wins
-- (later 10-Ks restate prior years as comparatives).
select cik, field, concept, accession_no, fiscal_year, value, filed
from {{ source('lake', 'xbrl_facts') }}
qualify row_number() over (
    partition by cik, fiscal_year, field order by filed desc, concept
) = 1
