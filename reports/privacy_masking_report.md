# Privacy Masking Report

This report demonstrates PHI-minimization patterns using synthetic data only. It is not a HIPAA compliance attestation.

## Summary

- Raw synthetic patient rows: 240
- Masked analytics rows: 240
- Direct names: excluded from the masked mart
- Patient IDs: tokenized with a deterministic hash prefix
- Phone numbers: converted to a boolean contact-method flag
- Postal codes: generalized to ZIP3 plus masking suffix
- A1c dates: bucketed to month
- A1c values: bucketed into analytic bands

## Masked Analytics Sample

| Masked patient key | Language | ZIP3 | Age band | A1c month | A1c band | Contact method | Outreach |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PAT-0037244255 | French | 606XX | 18-39 | 2026-04-01 | <7 | True | phone_or_sms |
| PAT-00B0C1032D | Spanish | 606XX | 40-64 | 2026-03-01 | 8-8.9 | True | phone_or_sms |
| PAT-025CEA329A | English | 606XX | 18-39 | 2024-05-01 | 7-7.9 | True | phone_or_sms |
| PAT-02FC3E95B2 | French | 606XX | 65+ | 2024-09-01 | 7-7.9 | True | phone_or_sms |
| PAT-045230846C | Arabic | 606XX | 65+ |  | missing | True | phone_or_sms |
| PAT-061996C680 | Spanish | 606XX | 18-39 |  | missing | False | mail_only |
| PAT-08C478C1DD | Spanish | 606XX | 40-64 |  | missing | True | phone_or_sms |
| PAT-08C832BCF1 | English | 606XX | 65+ | 2024-05-01 | <7 | True | phone_or_sms |
| PAT-0C661B1D03 | Spanish | 606XX | 40-64 | 2024-09-01 | <7 | True | phone_or_sms |
| PAT-0CC709B4C0 | Spanish | 606XX | 65+ | 2026-03-01 | 7-7.9 | True | phone_or_sms |

## Control Notes

- Bronze keeps raw synthetic payloads for lineage and debugging.
- Silver normalizes internal clinical entities.
- Gold analytics can default to `mart_masked_patient_panel` when direct identifiers are not needed.
- Production HIPAA controls would still require access policy, audit logging, encryption, environment hardening, BAAs, and formal risk assessment.
