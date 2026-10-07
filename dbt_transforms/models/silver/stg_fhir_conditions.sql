select
    source_system,
    resource_id as condition_id,
    replace(json_extract_string(raw_json, '$.subject.reference'), 'Patient/', '') as patient_id,
    json_extract_string(raw_json, '$.code.coding[0].code') as condition_code,
    json_extract_string(raw_json, '$.code.text') as condition_name,
    json_extract_string(raw_json, '$.clinicalStatus.coding[0].code') as clinical_status,
    cast(json_extract_string(raw_json, '$.onsetDateTime') as date) as onset_date,
    ingested_at
from {{ ref('brz_fhir_resources') }}
where resource_type = 'Condition'

