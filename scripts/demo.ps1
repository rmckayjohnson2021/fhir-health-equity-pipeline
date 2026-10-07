Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

uv run python -m scripts.generate_synthea_sample
uv run python -m scripts.ingest_fhir
uv run python -m scripts.ingest_unmapped_blobs --generate-sample --reset-table
Push-Location dbt_transforms
try {
    uv run dbt build --profiles-dir ../dbt_profiles
}
finally {
    Pop-Location
}
uv run python -m scripts.triage_quality_failures
uv run python -m scripts.review_gold_promotion
uv run python -m scripts.generate_dashboard_preview
uv run python -m scripts.generate_fhir_mapping_workbench
uv run python -m scripts.generate_privacy_report
uv run python -m scripts.version_data_release
