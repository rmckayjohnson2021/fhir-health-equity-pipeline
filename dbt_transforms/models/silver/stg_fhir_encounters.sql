select
    source_system,
    resource_id as encounter_id,
    replace(json_extract_string(raw_json, '$.subject.reference'), 'Patient/', '') as patient_id,
    json_extract_string(raw_json, '$.status') as encounter_status,
    json_extract_string(raw_json, '$.class.code') as encounter_class,
    cast(json_extract_string(raw_json, '$.period.start') as timestamp) as encounter_start_at,
    cast(json_extract_string(raw_json, '$.period.end') as timestamp) as encounter_end_at,
    ingested_at
from {{ ref('brz_fhir_resources') }}
where resource_type = 'Encounter'

