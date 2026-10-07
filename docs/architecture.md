# Architecture

This project is a local-first reference pipeline for synthetic healthcare data.

The core flow is:

1. Generate or load synthetic FHIR records.
2. Route records through source-specific adapters.
3. Preserve raw payloads in a bronze table.
4. Normalize key FHIR resources into silver tables.
5. Build gold marts for care gaps, outreach readiness, health-equity segmentation, and pipeline reliability.
6. Use dbt tests and a triage report to make data quality visible.

The v1 implementation should prioritize a reliable local demo over cloud deployment.
