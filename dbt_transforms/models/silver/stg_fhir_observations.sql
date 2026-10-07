select
    source_system,
    resource_id as observation_id,
    replace(json_extract_string(raw_json, '$.subject.reference'), 'Patient/', '') as patient_id,
    json_extract_string(raw_json, '$.status') as observation_status,
    json_extract_string(raw_json, '$.code.coding[0].code') as observation_code,
    json_extract_string(raw_json, '$.code.text') as observation_name,
    cast(json_extract_string(raw_json, '$.effectiveDateTime') as date) as effective_date,
    cast(json_extract_string(raw_json, '$.valueQuantity.value') as double) as value_quantity,
    json_extract_string(raw_json, '$.valueQuantity.unit') as value_unit,
    ingested_at
from {{ ref('brz_fhir_resources') }}
where resource_type = 'Observation'

