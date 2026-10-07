select *
from {{ ref('stg_fhir_observations') }}
where observation_code = '4548-4'
  and (value_quantity < 3.5 or value_quantity > 20)

