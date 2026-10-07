-- Health Equity and Care Gaps dashboard questions

-- Diabetes cohort by A1c care-gap status
select
    is_missing_recent_a1c,
    count(*) as patient_count
from main_gold.mart_diabetes_care_gaps
group by 1
order by 1;

-- Care gaps by preferred language
select
    preferred_language,
    count(*) as patient_count,
    sum(case when is_missing_recent_a1c then 1 else 0 end) as missing_recent_a1c_count
from main_gold.mart_diabetes_care_gaps
group by 1
order by missing_recent_a1c_count desc, patient_count desc;

-- Care gaps by age band
select
    age_band,
    count(*) as patient_count,
    sum(case when is_missing_recent_a1c then 1 else 0 end) as missing_recent_a1c_count
from main_gold.mart_diabetes_care_gaps
group by 1
order by age_band;

