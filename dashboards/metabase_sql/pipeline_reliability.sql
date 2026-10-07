-- Pipeline Reliability dashboard questions

-- Records loaded and quarantined by source system
select
    source_system,
    sum(records_seen) as records_seen,
    sum(records_loaded) as records_loaded,
    sum(records_quarantined) as records_quarantined
from main_gold.mart_pipeline_reliability
group by 1
order by records_quarantined desc, records_seen desc;

-- Quarantine rate by source system and resource type
select
    source_system,
    resource_type,
    records_seen,
    records_loaded,
    records_quarantined,
    quarantine_rate
from main_gold.mart_pipeline_reliability
order by quarantine_rate desc, records_seen desc;

