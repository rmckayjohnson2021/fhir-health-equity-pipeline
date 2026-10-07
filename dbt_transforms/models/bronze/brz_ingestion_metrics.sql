select
    source_system,
    resource_type,
    records_seen,
    records_loaded,
    records_quarantined,
    processed_at
from {{ source('bronze', 'ingestion_metrics') }}

