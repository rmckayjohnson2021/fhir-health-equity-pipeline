select
    source_system,
    resource_id as patient_id,
    json_extract_string(raw_json, '$.name[0].family') as family_name,
    json_extract_string(raw_json, '$.name[0].given[0]') as given_name,
    json_extract_string(raw_json, '$.gender') as gender,
    cast(json_extract_string(raw_json, '$.birthDate') as date) as birth_date,
    json_extract_string(raw_json, '$.communication[0].language.coding[0].code') as preferred_language_code,
    json_extract_string(raw_json, '$.communication[0].language.text') as preferred_language,
    json_extract_string(raw_json, '$.address[0].postalCode') as postal_code,
    json_extract_string(raw_json, '$.telecom[0].value') as phone,
    ingested_at
from {{ ref('brz_fhir_resources') }}
where resource_type = 'Patient'

