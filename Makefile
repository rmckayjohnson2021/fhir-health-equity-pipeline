.PHONY: demo batch-demo scenario-demo sample ingest unmapped-blobs dbt-build dbt-docs triage promotion-review dashboard-preview fhir-workbench privacy-report version-release clean

PYTHON ?= uv run python
DBT ?= uv run dbt

demo: sample ingest unmapped-blobs dbt-build triage promotion-review dashboard-preview fhir-workbench privacy-report version-release

batch-demo:
	$(PYTHON) -m scripts.run_batch_demo
	$(PYTHON) -m scripts.ingest_unmapped_blobs --generate-sample --reset-table
	cd dbt_transforms && $(DBT) build --profiles-dir ../dbt_profiles
	$(PYTHON) -m scripts.triage_quality_failures
	$(PYTHON) -m scripts.review_gold_promotion
	$(PYTHON) -m scripts.generate_dashboard_preview
	$(PYTHON) -m scripts.generate_fhir_mapping_workbench
	$(PYTHON) -m scripts.generate_privacy_report
	$(PYTHON) -m scripts.version_data_release

scenario-demo:
	$(PYTHON) -m scripts.generate_scenario_data
	$(PYTHON) -m scripts.ingest_fhir --input-dir data/scenario_raw
	$(PYTHON) -m scripts.ingest_unmapped_blobs --generate-sample --reset-table
	cd dbt_transforms && $(DBT) build --profiles-dir ../dbt_profiles || true
	$(PYTHON) -m scripts.triage_quality_failures
	$(PYTHON) -m scripts.review_gold_promotion
	$(PYTHON) -m scripts.generate_dashboard_preview || true
	$(PYTHON) -m scripts.generate_fhir_mapping_workbench || true
	$(PYTHON) -m scripts.generate_privacy_report || true
	$(PYTHON) -m scripts.version_data_release

sample:
	$(PYTHON) -m scripts.generate_synthea_sample

ingest:
	$(PYTHON) -m scripts.ingest_fhir

unmapped-blobs:
	$(PYTHON) -m scripts.ingest_unmapped_blobs --generate-sample --reset-table

dbt-build:
	cd dbt_transforms && $(DBT) build --profiles-dir ../dbt_profiles

dbt-docs:
	cd dbt_transforms && $(DBT) docs generate --profiles-dir ../dbt_profiles

triage:
	$(PYTHON) -m scripts.triage_quality_failures

promotion-review:
	$(PYTHON) -m scripts.review_gold_promotion

dashboard-preview:
	$(PYTHON) -m scripts.generate_dashboard_preview

fhir-workbench:
	$(PYTHON) -m scripts.generate_fhir_mapping_workbench

privacy-report:
	$(PYTHON) -m scripts.generate_privacy_report

version-release:
	$(PYTHON) -m scripts.version_data_release

clean:
	$(PYTHON) -m scripts.ingest_fhir --clean-only
