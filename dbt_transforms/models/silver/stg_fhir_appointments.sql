select
    source_system,
    resource_id as appointment_id,
    replace(json_extract_string(raw_json, '$.participant[0].actor.reference'), 'Patient/', '') as patient_id,
    json_extract_string(raw_json, '$.status') as appointment_status,
    cast(json_extract_string(raw_json, '$.start') as timestamp) as appointment_start_at,
    ingested_at
from {{ ref('brz_fhir_resources') }}
where resource_type = 'Appointment'

