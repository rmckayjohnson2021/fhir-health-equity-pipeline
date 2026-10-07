with metrics as (
    select
        source_system,
        resource_type,
        sum(records_seen) as records_seen,
        sum(records_loaded) as records_loaded,
        sum(records_quarantined) as records_quarantined,
        max(processed_at) as processed_at
    from {{ ref('brz_ingestion_metrics') }}
    group by 1, 2
)

select
    source_system,
    resource_type,
    records_seen,
    records_loaded,
    records_quarantined,
    case
        when records_seen = 0 then 0
        else records_loaded::double / records_seen
    end as load_success_rate,
    case
        when records_seen = 0 then 0
        else records_quarantined::double / records_seen
    end as quarantine_rate,
    processed_at
from metrics
