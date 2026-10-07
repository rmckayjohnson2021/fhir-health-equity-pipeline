# Full Feature Demo Script

Use this script when you want to demonstrate every major capability in the repository from a clean local run through governance, observability, dashboarding, and production-readiness discussion.

## 1. Start With the Platform Claim

Talk track:

> This is a local-first synthetic healthcare data platform. It simulates multi-source FHIR ingestion, lands valid resources into DuckDB, quarantines unsafe records, transforms FHIR-shaped JSON with dbt, applies quality gates, and produces health-equity, pipeline reliability, privacy, and governance artifacts. It uses synthetic data only and does not claim real EHR integration.

Open:

```text
README.md
docs/architecture.md
docs/source-system-mapping.md
```

Point out:

- The source feeds are simulated adapters.
- The repo stays low-cost and runnable with DuckDB and dbt Core.
- The dashboard is generated from local marts, not manually mocked.

## 2. Run the Baseline Demo

Run:

```powershell
.\scripts\demo.ps1
```

Expected result:

- 347 valid synthetic FHIR resources loaded.
- 1 intentionally invalid Observation quarantined.
- dbt build succeeds.
- 39 dbt tests pass.
- Dashboard, FHIR workbench, reports, privacy artifacts, and last-known-good pointer are refreshed.

Open:

```text
reports/data_quality_triage.md
reports/last_known_good.md
```

Explain:

- The warehouse has a current successful run.
- Quarantine is visible instead of silent.
- Last-known-good gives the demo a rollback/release-governance story.

## 3. Show Source Generation and Ingestion

Open:

```text
scripts/generate_synthea_sample.py
scripts/ingest_fhir.py
```

Explain:

- The default panel is 60 synthetic patients.
- Preferred languages are English, Spanish, French, Haitian Creole, and Arabic.
- Simulated source systems are `epic_simulated`, `athena_simulated`, and `legacy_pms_simulated`.
- The ingestion layer validates required routing fields, lands valid records, and writes invalid records to quarantine.

Useful command:

```powershell
uv run python -m scripts.generate_synthea_sample --patient-count 60
uv run python -m scripts.ingest_fhir --trace-mappings --trace-delay-seconds 0.02
```

Explain:

- Mapping traces show how source JSON paths become model-facing fields.
- Quarantined records show a reason instead of disappearing.

## 4. Walk the dbt Layers

Open:

```text
dbt_transforms/models/bronze/
dbt_transforms/models/silver/
dbt_transforms/models/gold/
dbt_transforms/models/schema.yml
dbt_transforms/tests/a1c_values_are_plausible.sql
```

Explain:

- Bronze mirrors raw FHIR resources and ingestion metrics.
- Silver normalizes patients, conditions, observations, encounters, appointments, and communications.
- Gold creates care-gap, pipeline reliability, and masked patient-panel marts.
- dbt tests cover identity, relationships, accepted values, and plausible clinical values.

Run:

```powershell
Push-Location dbt_transforms
uv run dbt build --profiles-dir ../dbt_profiles
Pop-Location
```

## 5. Demonstrate the Dashboard Views

Open:

```powershell
Start-Process .\dashboards\static_preview.html
```

Show:

- Launch `System Health` modal.
- `Current State` view.
- `What's in process` view.
- `Detailed view`.

Explain:

- The launch modal gives a fast health check: run fidelity, loaded resources, quarantine count, care-gap signal, and source feed count.
- Current State is the executive summary.
- What's in process shows operational movement and source reliability.
- Detailed view exposes all panels and the patient-level table.
- Hover windows explain source feeds, metrics, and pipeline layers.
- The patient detail table supports search, status/language/date filters, paging, sorting, and CSV export.

## 6. Demonstrate the Pipeline Monitor

In the dashboard, click:

```text
Open pipeline monitor
```

Show:

- `Run slow monitor`
- `Run next synthetic load`
- `Restart` actions
- `Dismiss all quarantined`
- Event log
- OpenTelemetry Trace Dashboard panel

Explain:

- The slow monitor simulates a real-time batch run through ingest, transform, quality, and promotion stages.
- `Run next synthetic load` works when the dashboard is served through `uv run python -m scripts.dashboard_control_server`; it triggers the next local synthetic load and refreshes generated artifacts.
- Restart actions are browser-side simulations of what would be orchestrator/runbook actions in production.
- Dismiss all quarantined simulates exporting active quarantine records to an archive for later stewardship and leaves gold marts unchanged.
- The OpenTelemetry Trace Dashboard turns local span events into a readable waterfall with status, duration, and attributes.

## 7. Demonstrate Micro-Batches, Tracing, OpenTelemetry, and Chaos

Run:

```powershell
.\scripts\batch_demo.ps1 -DelaySeconds 2 -BatchSize 10
```

Explain:

- This makes the local run easier to watch.
- Batches print cumulative loaded and quarantined counts.

Run:

```powershell
.\scripts\batch_demo.ps1 -TraceMappings
```

Explain:

- Mapping traces show how records move toward analytics models.

Run:

```powershell
.\scripts\batch_demo.ps1 -OtelConsole -ChaosScenario missing_id
```

Explain:

- OpenTelemetry console spans are local and free.
- The chaos injector adds a controlled bad event so the error path is visible.
- The dashboard trace panel shows the same pattern without requiring a paid tracing backend.

## 8. Demonstrate Gold Promotion Review

Open:

```text
reports/gold_promotion_review.md
reports/gold_promotion_decisions.jsonl
scripts/review_gold_promotion.py
```

Explain:

- Bronze landing is not automatic approval for gold marts.
- Records blocked by quarantine or dbt issues enter a review queue.
- Recommended decisions are generated for repeatable demos.

Optional interactive mode:

```powershell
uv run python -m scripts.review_gold_promotion --interactive
```

## 9. Demonstrate Privacy and Masking

Open:

```text
dbt_transforms/models/gold/mart_masked_patient_panel.sql
reports/privacy_masking_report.md
```

Explain:

- Patient identifiers are tokenized.
- Direct names and phone numbers are excluded from the masked mart.
- Postal codes are generalized.
- Dates are bucketed and A1c values are banded.
- This demonstrates privacy-minimization patterns on synthetic data; it is not a HIPAA attestation.

## 10. Demonstrate Unmapped Blob Provenance

Open:

```text
scripts/ingest_unmapped_blobs.py
reports/unmapped_source_drawer.md
```

Explain:

- Not every source payload maps cleanly to FHIR on day one.
- Unmapped blobs are retained with hashes, source paths, content type, and semantic hints.
- They are excluded from gold marts until a governed mapping exists.

## 11. Demonstrate the FHIR Mapping Workbench

Open:

```powershell
Start-Process .\dashboards\fhir_mapping_workbench.html
```

Show:

- FHIR version selector: R4, R4B, R5.
- Search for `Observation`.
- Select each unmapped blob.
- Compare blocked, candidate, and supported mappings.
- Use `Simulate but do not apply`.
- Try a forced conversion without a note.
- Add a note and record the simulated decision.
- Start `uv run python -m scripts.dashboard_control_server`, reopen the workbench from `http://127.0.0.1:8765/dashboards/fhir_mapping_workbench.html`, and record a decision to persist a local policy.
- Click `Revert policy for future loads`.

Explain:

- Older FHIR versions have less local support.
- R5 can support mappings that are blocked or candidate-only in older profiles.
- Simulation shows projected care-gap impact without changing data.
- Forced conversions require an audit note and a selected target FHIR type.
- Persisted migration decisions are timestamp-forward only. Previous runs stay unchanged unless an explicit replay/backfill is run.
- Revert is also a recorded future-effective policy decision, not a hidden edit of history.

## 12. Demonstrate Scenario-Rich Data

Run:

```powershell
.\scripts\scenario_demo.ps1 -PatientCount 250
```

Explain:

- This creates a larger deterministic scenario dataset with expected real-world data issues.
- Examples include stale labs, missing language, missing postal code, duplicate identifiers, malformed JSON, unsupported resources, wrong units, and implausible values.
- Dirty scenario runs can generate blockers without replacing the last-known-good pointer.

## 13. Show Contract Tests and CI Guardrails

Run:

```powershell
uv run python -m unittest discover -s tests
```

Open:

```text
tests/test_portfolio_contract.py
.github/workflows/ci.yml
```

Explain:

- Tests guard simple portfolio regressions: expected source systems, expected languages, dashboard controls, FHIR version labels, forced-conversion behavior, and README screenshot references.
- GitHub Actions runs the full local demo plus contract tests.

## 14. Close With the Production Readiness Discussion

Close with:

> This repo is intentionally local and synthetic. To make this production usable, the pattern would need real governed source contracts, formal FHIR validation, orchestration, cloud storage/warehouse controls, access control, PHI/HIPAA operating controls, observability, SLAs, incident response, deployment automation, and a signed clinical/data-governance process.

Then point to:

```text
README.md#what-would-make-this-production-usable
docs/operating-model.md
docs/cloud-platform-readiness.md
docs/bigquery-readiness.md
```
