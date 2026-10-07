# Data Quality Triage Report

This report is generated from dbt artifacts after the local demo build.

## Summary

- Total dbt test results: 39
- Failing or warning tests: 0
- Source/resource groups with quarantined records: 1

## Ingestion Quarantine

| Source system | Resource type | Seen | Loaded | Quarantined | Suggested next step |
|---|---:|---:|---:|---:|---|
| `legacy_pms_simulated` | `Observation` | 17 | 16 | 1 | Inspect the quarantine NDJSON and decide whether to correct the source mapping or reject the feed record. |

## Findings

No failing dbt tests were detected in the latest run.

This does not prove the data is production-ready. It means the current synthetic fixture passed the v1 checks for identity, referential integrity, accepted values, and clinical plausibility.

