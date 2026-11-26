select
    cik,
    trim(name) as company_name,
    upper(ticker) as ticker,
    sic_code,
    coalesce(sector, 'Unclassified') as sector
from {{ source('lake', 'companies') }}
where cik <> 0  -- synthetic-invoice pseudo company
