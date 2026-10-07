with patients as (
    select * from {{ ref('stg_fhir_patients') }}
),

diabetes_conditions as (
    select distinct patient_id
    from {{ ref('stg_fhir_conditions') }}
    where condition_code = '44054006'
),

a1c_observations as (
    select
        patient_id,
        max(effective_date) as last_a1c_date,
        max_by(value_quantity, effective_date) as last_a1c_value
    from {{ ref('stg_fhir_observations') }}
    where observation_code = '4548-4'
    group by patient_id
)

select
    p.patient_id,
    p.source_system,
    p.preferred_language_code,
    p.preferred_language,
    p.postal_code,
    date_diff('year', p.birth_date, current_date) as age_years,
    case
        when date_diff('year', p.birth_date, current_date) < 40 then '18-39'
        when date_diff('year', p.birth_date, current_date) < 65 then '40-64'
        else '65+'
    end as age_band,
    a.last_a1c_date,
    a.last_a1c_value,
    case
        when a.last_a1c_date is null then true
        when a.last_a1c_date < current_date - interval 1 year then true
        else false
    end as is_missing_recent_a1c,
    case
        when p.phone is not null then 'phone_or_sms'
        else 'mail_only'
    end as outreach_channel
from patients p
inner join diabetes_conditions d
    on p.patient_id = d.patient_id
left join a1c_observations a
    on p.patient_id = a.patient_id

