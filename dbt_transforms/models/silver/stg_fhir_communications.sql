select
    source_system,
    resource_id as communication_id,
    replace(json_extract_string(raw_json, '$.subject.reference'), 'Patient/', '') as patient_id,
    json_extract_string(raw_json, '$.status') as communication_status,
    json_extract_string(raw_json, '$.medium[0].coding[0].code') as communication_channel,
    cast(json_extract_string(raw_json, '$.sent') as timestamp) as sent_at,
    ingested_at
from {{ ref('brz_fhir_resources') }}
where resource_type = 'Communication'

