# Demo Script

Use this script to present the project in a live interview or portfolio walkthrough.

## Setup

Open the repository root:

```powershell
cd path\to\fhir-health-equity-pipeline
```

Start with the one-command demo:

```powershell
.\scripts\demo.ps1
```

Expected result:

- 347 synthetic FHIR resources loaded across 60 synthetic patients.
- 1 intentionally invalid record quarantined.
- dbt build succeeds.
- 39 dbt tests pass.
- `reports/data_quality_triage.md` is generated.
- `reports/gold_promotion_review.md` is generated.
- `reports/privacy_masking_report.md` is generated.
- `reports/unmapped_source_drawer.md` is generated.
- `reports/last_known_good.md` is generated.
- `dashboards/static_preview.html` is generated.
- `dashboards/fhir_mapping_workbench.html` is generated.

## Two Minute Talk Track

This repo is a local-first synthetic healthcare data platform. It simulates multi-source FHIR ingestion, lands valid resources in DuckDB, quarantines bad records, transforms FHIR JSON into dbt models, applies quality tests, and produces health-equity and pipeline reliability analytics.

The project is intentionally narrow. It does not claim real EHR integration or production HIPAA readiness. It demonstrates the platform pattern: source routing, raw landing, normalization, quality gates, operational metrics, and stakeholder-ready reporting.

## What To Show

### 1. Source and Ingestion

Open:

```text
scripts/generate_synthea_sample.py
scripts/ingest_fhir.py
```

Explain:

- The source systems are simulated.
- The records are synthetic FHIR-shaped JSON.
- Valid records land in bronze.
- Invalid records are quarantined and counted.
- Unmapped text/JSON blobs land in a separate provenance drawer, not the FHIR bronze table.

### 2. dbt Models

Open:

```text
dbt_transforms/models/bronze/
dbt_transforms/models/silver/
dbt_transforms/models/gold/
```

Explain:

- Bronze preserves landed resources and metrics.
- Silver normalizes FHIR resources into relational entities.
- Gold creates stakeholder-facing marts for care gaps and reliability.

### 3. Quality Gates

Open:

```text
dbt_transforms/models/schema.yml
dbt_transforms/tests/a1c_values_are_plausible.sql
reports/data_quality_triage.md
```

Explain:

- dbt tests cover uniqueness, not-null checks, relationships, accepted values, and plausible A1c values.
- The triage report summarizes dbt results and ingestion quarantine metrics.

### 4. Dashboard

Open:

```text
dashboards/static_preview.html
```

Explain:

- The dashboard is generated from DuckDB gold marts.
- It shows care-gap analytics and pipeline reliability.
- The visual is a static portfolio artifact, not a manually mocked screenshot.
- Hover windows explain the source feeds, pipeline layers, and KPI assumptions without leaving the dashboard.
- The patient detail table supports search, language/status/date filters, paging, sorting, and CSV export.
- The run fidelity trend compares the current run against recent local last-known-good baselines.

### 5. Micro-Batch Processing

Run:

```powershell
.\scripts\batch_demo.ps1
```

Explain:

- The script processes synthetic source batches with a configurable delay so the run is easier to watch.
- It prints cumulative operational metrics after each batch.
- It then refreshes dbt models, triage, and the dashboard.
- This demonstrates incremental processing without adding Kafka or orchestration infrastructure to v1.

To slow the run down further:

```powershell
.\scripts\batch_demo.ps1 -DelaySeconds 2 -BatchSize 10
```

For a more operational walkthrough, run:

```powershell
.\scripts\batch_demo.ps1 -TraceMappings
```

Explain:

- The trace shows each synthetic FHIR record as it maps from source JSON paths into dbt-facing model columns.
- Records that cannot be safely loaded show a quarantine reason instead of silently disappearing.

To add observability and a bounded failure:

```powershell
.\scripts\batch_demo.ps1 -OtelConsole -ChaosScenario missing_id
```

Explain:

- OpenTelemetry spans are emitted to the console for batches, source files, loaded resources, and quarantined resources.
- The chaos injector adds a controlled synthetic bad event so the trace includes an error path.
- The dashboard preview includes an OpenTelemetry Trace Dashboard that presents the same run pattern as a local span waterfall.
- This stays local and free; no paid monitoring backend is required.

### 6. Gold Promotion Review

Open:

```text
reports/gold_promotion_review.md
reports/gold_promotion_decisions.jsonl
```

Explain:

- Bronze landing is not the same as approval for stakeholder reporting.
- Records blocked by ingestion quarantine or dbt test failures go into a gold-promotion review queue.
- The default report recommends decisions automatically for repeatable demos.
- The same logic can run in interactive mode:

```powershell
uv run python -m scripts.review_gold_promotion --interactive
```

### 7. Privacy and Provenance Controls

Open:

```text
dbt_transforms/models/gold/mart_masked_patient_panel.sql
reports/privacy_masking_report.md
reports/unmapped_source_drawer.md
reports/last_known_good.md
```

Explain:

- The masked mart tokenizes patient identifiers and removes direct names and phone numbers.
- ZIP codes are generalized, dates are bucketed, and A1c values are banded for analytics.
- Unmapped blobs are retained with hashes and semantic hints for future mapping, but excluded from gold marts.
- Successful runs are snapshotted as last-known-good local data releases.
- These are synthetic-data privacy patterns, not a claim of production HIPAA compliance.

### 8. Pipeline Monitor Modal

Open:

```text
dashboards/static_preview.html
```

Click `Open pipeline monitor`.

Explain:

- The modal shows local pipeline status, quarantine count, stalled checks, and pipeline-level actions.
- The `Run slow monitor` control animates a browser-side batch run through ingest, transform, quality, and gold promotion stages.
- The `Dismiss all quarantined` action simulates exporting active quarantine records to an archive for later stewardship without changing gold marts.
- Restart actions are simulated and logged in the browser as an operator workflow.
- The OpenTelemetry Trace Dashboard panel shows span duration, status, attributes, and the quarantine/error path without a hosted tracing service.
- In production, those controls would call an orchestrator or incident runbook instead of restarting directly from a static dashboard.

### 9. FHIR Mapping Workbench

Open:

```text
dashboards/fhir_mapping_workbench.html
```

Explain:

- The workbench queries a local demo schema subset for FHIR R4, R4B, and R5.
- Operators can select an unmapped blob, inspect candidate mappings, and see whether a field is blocked, candidate-only, or supported under the selected version.
- The `Simulate but do not apply` button shows a projected care-gap signal change without changing data.
- The migration decision control requires an effective timestamp; forced mappings require an audit note.
- The version labels follow HL7's published sequence: R4 `4.0`, R4B `4.3`, and R5 `5.0`.

### 10. Scenario-Rich Data

Run:

```powershell
.\scripts\scenario_demo.ps1 -PatientCount 250
```

Explain:

- This creates a larger deterministic dataset with expected real-world issues.
- Examples include stale labs, missing language, missing postal code, duplicate identifiers, malformed JSON, unsupported resources, wrong units, and implausible values.
- Dirty scenario runs can generate blockers without replacing the last-known-good pointer.

## Deep-Dive Questions To Invite

- Where would orchestration fit?
- How would this scale to BigQuery, Snowflake, or Databricks?
- Which failures should quarantine records versus fail dbt?
- Which failures should block promotion to gold marts?
- What would production monitoring include?
- When is a forced semantic mapping acceptable, and who approves it?
- How would access control differ between bronze, silver, and gold?
- What would change if the project had millions of records per day?

## Closing Statement

The value of this project is not tool volume. The value is the end-to-end platform pattern: source routing, raw landing, tested transformations, quality triage, operational metrics, and analytics that connect technical pipeline work to healthcare outcomes.
