# Interview Walkthrough

Use this guide to explain the project clearly without overclaiming. The goal is to show healthcare data platform judgment, not to pretend this small repo is a production Medicaid platform.

## 30 Second Version

I built a local-first synthetic healthcare data platform that simulates multi-source FHIR ingestion, validates and quarantines bad records, transforms raw FHIR JSON into tested dbt models, and produces health-equity care-gap and pipeline reliability analytics. It runs locally with DuckDB and dbt, uses synthetic data only, and includes platform leadership artifacts such as KPIs, cost notes, architecture decisions, and an operating model.

## 2 Minute Version

This project demonstrates how I think about healthcare data platforms from ingestion through stakeholder analytics.

The source data is synthetic FHIR-shaped NDJSON from three simulated source systems. The ingestion layer tags each source, validates basic routing requirements, loads valid records into DuckDB bronze tables, quarantines invalid records, and emits ingestion metrics.

dbt then models the data in bronze, silver, and gold layers. Bronze preserves the raw landed records. Silver normalizes FHIR resources such as patients, encounters, conditions, observations, appointments, and communications. Gold creates two stakeholder-facing marts: one for diabetes A1c care gaps and one for pipeline reliability.

The project also includes dbt tests for identity, referential integrity, accepted values, and clinically plausible A1c values. A deterministic triage script reads dbt artifacts and ingestion metrics to produce a Markdown quality report.

The static dashboard preview is generated from the gold marts, so the visual story comes from the same data pipeline. The repo is intentionally local-first and low-cost, but the docs explain how the pattern could scale to BigQuery, Snowflake, Databricks, orchestration, and production monitoring.

## 5 Minute Technical Walkthrough

Start with the command:

```powershell
.\scripts\demo.ps1
```

That command proves the full loop:

1. Generate deterministic synthetic FHIR-shaped records.
2. Ingest valid records into DuckDB.
3. Quarantine invalid records.
4. Run dbt build.
5. Generate a data quality triage report.
6. Generate a static dashboard preview.

To show incremental processing, run:

```powershell
.\scripts\batch_demo.ps1
```

That command processes three micro-batches, prints cumulative operational metrics after each batch, then refreshes dbt models, the triage report, and the dashboard preview.

Then explain the layers:

- `scripts/generate_synthea_sample.py`: creates the tiny synthetic FHIR fixture.
- `scripts/ingest_fhir.py`: simulates adapter and integration-engine responsibilities.
- `scripts/run_batch_demo.py`: simulates near-real-time micro-batch ingestion.
- `dbt_transforms/models/bronze`: exposes raw landing tables to dbt.
- `dbt_transforms/models/silver`: extracts FHIR JSON into relational clinical entities.
- `dbt_transforms/models/gold`: creates care-gap and reliability marts.
- `dbt_transforms/models/schema.yml`: defines generic dbt tests.
- `dbt_transforms/tests/a1c_values_are_plausible.sql`: defines a custom clinical plausibility test.
- `scripts/triage_quality_failures.py`: turns dbt and ingestion results into an investigation report.
- `scripts/generate_dashboard_preview.py`: creates a polished static dashboard from the marts.

## What To Emphasize

- This is synthetic data only.
- The source systems are simulated and do not claim real vendor integration.
- The project prioritizes reliability, clarity, and cost control over tool sprawl.
- The key platform pattern is route, validate, land raw, normalize, test, report, and monitor.
- The dashboard is generated from modeled marts, not manually mocked.
- The docs show leadership thinking: architecture decisions, KPIs, cost/ROI, and operating model.

## How This Maps To A Data Engineering Leader Role

### Architecture

The repo demonstrates tradeoff-aware platform design. It starts with DuckDB for a low-cost local demo and documents how the pattern can map to BigQuery, Snowflake, or Databricks.

### Quality

Quality exists in two places. Ingestion quarantine stops bad records early, while dbt tests protect modeled analytics. The triage report makes failures easier to investigate.

### Operations

The pipeline reliability mart tracks records seen, loaded, quarantined, load success rate, and quarantine rate. Those are simple local metrics, but they map to production monitoring concepts.

### Stakeholder Value

The care-gap mart and dashboard preview translate technical pipeline work into health-equity and outreach analytics.

### Cost And ROI

The project avoids paid services for v1. The cost documentation explains how cloud spend would be evaluated later through workload size, freshness requirements, query patterns, and self-service analytics needs.

## Good Interview Questions To Invite

- How would this change if the data volume were 100 million records per day?
- Where would orchestration fit?
- What would you monitor in production?
- What belongs in an integration engine versus dbt?
- How would you adapt this for BigQuery, Snowflake, or Databricks?
- How would you govern access to raw versus modeled healthcare data?
- How would you decide whether a data quality issue should quarantine the record or fail the dbt build?

## Honest Limitations

- It is not HIPAA-compliant production software.
- It does not use real patient data.
- It does not integrate with real EHR vendor APIs.
- It does not run a production orchestration system.
- The care-gap logic is illustrative and not clinical guidance.
- The dataset is intentionally tiny so the project stays runnable and easy to review.

## Closing Line

The point of this repo is not that DuckDB and a few scripts replace an enterprise healthcare data platform. The point is that the repo demonstrates the same operating patterns: source routing, raw landing, normalization, testing, quality triage, platform metrics, stakeholder analytics, and cost-aware architecture.
