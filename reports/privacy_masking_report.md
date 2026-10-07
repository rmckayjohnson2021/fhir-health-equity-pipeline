# Privacy Masking Report

This report demonstrates PHI-minimization patterns using synthetic data only. It is not a HIPAA compliance attestation.

## Summary

- Raw synthetic patient rows: 60
- Masked analytics rows: 60
- Direct names: excluded from the masked mart
- Patient IDs: tokenized with a deterministic hash prefix
- Phone numbers: converted to a boolean contact-method flag
- Postal codes: generalized to ZIP3 plus masking suffix
- A1c dates: bucketed to month
- A1c values: bucketed into analytic bands

## Masked Analytics Sample

| Masked patient key | Language | ZIP3 | Age band | A1c month | A1c band | Contact method | Outreach |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PAT-0C661B1D03 | Spanish | 606XX | 40-64 | 2026-05-01 | 8-8.9 | True | phone_or_sms |
| PAT-1156BC1DFA | Spanish | 606XX | 40-64 | 2024-05-01 | <7 | True | phone_or_sms |
| PAT-12DAE3D29A | French | 606XX | 18-39 |  | missing | True | phone_or_sms |
| PAT-15F6443503 | English | 606XX | 65+ | 2026-04-01 | <7 | True | phone_or_sms |
| PAT-1B4029470C | French | 606XX | 40-64 |  | missing | False | mail_only |
| PAT-1F46761996 | Spanish | 606XX | 18-39 | 2026-05-01 | 8-8.9 | True | phone_or_sms |
| PAT-219315CB83 | Spanish | 606XX | 18-39 | 2024-01-01 | 8-8.9 | False | mail_only |
| PAT-2636FD0CF5 | English | 606XX | 40-64 | 2024-09-01 | 7-7.9 | False | mail_only |
| PAT-38D5E58C57 | Arabic | 606XX | 40-64 | 2026-03-01 | <7 | True | phone_or_sms |
| PAT-3FF4F52809 | English | 606XX | 65+ | 2026-02-01 | <7 | True | phone_or_sms |

## Control Notes

- Bronze keeps raw synthetic payloads for lineage and debugging.
- Silver normalizes internal clinical entities.
- Gold analytics can default to `mart_masked_patient_panel` when direct identifiers are not needed.
- Production HIPAA controls would still require access policy, audit logging, encryption, environment hardening, BAAs, and formal risk assessment.
