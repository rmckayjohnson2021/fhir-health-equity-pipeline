with care_gaps as (
    select * from {{ ref('mart_diabetes_care_gaps') }}
),

patients as (
    select
        patient_id,
        phone
    from {{ ref('stg_fhir_patients') }}
)

select
    concat('PAT-', upper(left(sha256(c.patient_id), 10))) as masked_patient_key,
    c.source_system,
    c.preferred_language_code,
    c.preferred_language,
    case
        when c.postal_code is null then null
        else concat(left(c.postal_code, 3), 'XX')
    end as zip3_masked,
    c.age_band,
    case
        when c.last_a1c_date is null then null
        else cast(date_trunc('month', c.last_a1c_date) as date)
    end as last_a1c_month,
    case
        when c.last_a1c_value is null then 'missing'
        when c.last_a1c_value < 7 then '<7'
        when c.last_a1c_value < 8 then '7-7.9'
        when c.last_a1c_value < 9 then '8-8.9'
        else '9+'
    end as a1c_value_band,
    c.is_missing_recent_a1c,
    case
        when p.phone is not null then true
        else false
    end as has_contact_method,
    c.outreach_channel
from care_gaps c
left join patients p
    on c.patient_id = p.patient_id
