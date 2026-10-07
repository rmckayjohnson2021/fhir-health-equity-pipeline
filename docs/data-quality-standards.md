# Data Quality Standards

This project uses synthetic data only, but it still models practical healthcare data quality controls.

## Ingestion Standards

- Every accepted record must have a known simulated source system.
- Every accepted record must have a supported FHIR resource type.
- Every accepted record must have a FHIR resource id.
- Invalid records are written to quarantine instead of silently dropped.
- Ingestion metrics are emitted by source system and resource type.

## Modeling Standards

- Patient ids must be unique and not null.
- Encounters, conditions, observations, appointments, and communications must reference valid patients.
- Source systems and resource types must match accepted value sets.
- A1c observations must use the expected LOINC code and percent unit in the v1 fixture.
- A1c values must stay within a configured plausible range.

## Governance Notes

Passing tests do not make the project production-ready or clinically authoritative. They show that the demo pipeline has explicit assumptions, quality gates, and failure visibility.

