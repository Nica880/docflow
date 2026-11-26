select sector, count(*) as n_companies
from {{ ref('dim_company') }}
group by sector
