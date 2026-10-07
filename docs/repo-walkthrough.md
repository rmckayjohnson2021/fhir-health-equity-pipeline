# Repo Walkthrough

This walkthrough explains the project in the order a data engineering leader, analytics engineer, or interviewer should read it.

## 1. The demo command

Start with:

```powershell
.\scripts\demo.ps1
```

This command is the walking skeleton. It proves the repo can run end to end:

1. Generate synthetic FHIR-shaped source records.
2. Ingest records into DuckDB.
3. Quarantine invalid records.
4. Build dbt models.
5. Run dbt tests.
6. Generate a data quality triage report.

Platform point: a portfolio data platform should have one reliable command that demonstrates the core workflow.

## 2. Synthetic data generation

File: `scripts/generate_synthea_sample.py`

This script creates tiny deterministic FHIR-shaped NDJSON files for three simulated source systems:

- `epic_simulated`
- `athena_simulated`
- `legacy_pms_simulated`

It creates Patients, Encounters, Conditions, Observations, Appointments, and Communications. It also creates one intentionally invalid Observation with no FHIR id.

Platform point: synthetic data lets the project demonstrate healthcare patterns without PHI risk or paid services.

## 3. Ingestion and quarantine

File: `scripts/ingest_fhir.py`

The ingestion script performs the responsibilities that an integration layer often owns:

- identify the source system
- validate supported resource types
- require a resource id
- load valid records into bronze
- quarantine invalid records
- emit ingestion metrics

Valid records land in `bronze.raw_fhir_resources`. Invalid records are written under `data/quarantine/`.

Platform point: good data platforms do not let every malformed source record flow into analytics. They preserve raw data, separate invalid records, and make feed quality measurable.

## 3A. Micro-batch simulation

Files:

- `scripts/run_batch_demo.py`
- `scripts/batch_demo.ps1`

The batch demo processes the same synthetic patients as three small source batches. After each batch, it prints cumulative loaded and quarantined counts by source system. This simulates near-real-time operational visibility without adding Kafka, Airflow, or cloud infrastructure to v1.

Platform point: a simple local project can still demonstrate an important production pattern: land incremental source data, update operational metrics, and rebuild trusted downstream models.

## 4. Bronze models

Folder: `dbt_transforms/models/bronze/`

Bronze dbt models expose the raw DuckDB ingestion tables to dbt:

- `brz_fhir_resources`
- `brz_ingestion_metrics`

These models do not apply much business logic. They make the raw landing layer available for lineage, tests, and downstream transforms.

Platform point: bronze is for preservation and traceability, not heavy interpretation.

## 5. Silver models

Folder: `dbt_transforms/models/silver/`

Silver models convert raw FHIR JSON into relational models:

- `stg_fhir_patients`
- `stg_fhir_encounters`
- `stg_fhir_conditions`
- `stg_fhir_observations`
- `stg_fhir_appointments`
- `stg_fhir_communications`

These models extract ids, references, dates, codes, values, demographics, and communication fields from raw JSON.

Platform point: silver is where raw healthcare records become queryable, testable analytics entities.

## 6. Gold marts

Folder: `dbt_transforms/models/gold/`

Gold models answer stakeholder-facing questions:

- `mart_diabetes_care_gaps` identifies the diabetes cohort and flags missing or stale A1c results.
- `mart_pipeline_reliability` summarizes records seen, loaded, quarantined, load success rate, and quarantine rate.

Platform point: gold models should be shaped around decisions. One mart speaks to care-gap analytics; the other speaks to platform operations.

## 7. Data quality tests

Files:

- `dbt_transforms/models/schema.yml`
- `dbt_transforms/tests/a1c_values_are_plausible.sql`

The dbt tests check:

- not-null ids
- uniqueness
- referential integrity back to patients
- accepted source systems
- accepted resource types
- accepted observation codes and units
- plausible A1c values

Platform point: data quality is not a final manual review. It is encoded into the build so quality expectations run every time.

## 8. Quality triage report

File: `scripts/triage_quality_failures.py`

Output: `reports/data_quality_triage.md`

The report reads dbt artifacts and ingestion metrics. It summarizes:

- total dbt tests
- failing or warning tests
- quarantined source/resource groups
- likely causes and next steps when tests fail

Platform point: a data platform should help humans investigate problems, not merely fail with raw logs.

## 9. Dashboard SQL

Folder: `dashboards/metabase_sql/`

The saved SQL files represent the first BI layer:

- health equity and care gaps
- pipeline reliability

These can be copied into Metabase or used as the basis for screenshots.

Platform point: dashboard artifacts should be tied to modeled marts, not one-off raw queries.

## 10. Leadership docs

Folder: `docs/`

The docs explain how the small technical demo maps to leadership concerns:

- `architecture-decisions.md` explains tradeoffs.
- `data-quality-standards.md` defines quality expectations.
- `platform-kpis.md` defines platform health metrics.
- `cost-and-roi.md` explains why v1 is local-first and how cloud costs would be evaluated.
- `operating-model.md` explains ownership, intake, incident response, and team standards.
- `cloud-platform-readiness.md` explains how the pattern could map to BigQuery, Snowflake, Databricks, or orchestration.

Platform point: senior data engineering work is not only code. It is also decision framing, operating discipline, stakeholder clarity, and cost-aware design.

## Interview Talk Track

Use this concise explanation:

> I built a local-first synthetic healthcare data platform that simulates multi-source FHIR ingestion, applies ingestion quarantine and dbt quality gates, normalizes clinical records into silver models, and produces gold marts for diabetes care gaps and pipeline reliability. I kept v1 intentionally small so it is runnable, but added architecture decisions, KPIs, cost notes, and an operating model to show how I think about data platform leadership.
