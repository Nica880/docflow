{% test dbt_utils_unique_combination(model, columns) %}
-- Minimal local version of dbt_utils.unique_combination_of_columns (no package download needed).
select {{ columns | join(', ') }}, count(*) as n
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}
