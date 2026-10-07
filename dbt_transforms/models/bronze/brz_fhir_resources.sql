select
    source_system,
    resource_type,
    resource_id,
    ingested_at,
    source_file,
    raw_json
from {{ source('bronze', 'raw_fhir_resources') }}

