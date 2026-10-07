param(
    [int]$PatientCount = 250,
    [int]$Seed = 20261007,
    [switch]$TraceMappings,
    [switch]$OtelConsole
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

uv run python -m scripts.generate_scenario_data --patient-count $PatientCount --seed $Seed

$ingestArgs = @("-m", "scripts.ingest_fhir", "--input-dir", "data/scenario_raw")
if ($TraceMappings) {
    $ingestArgs += "--trace-mappings"
    $ingestArgs += "--trace-delay-seconds"
    $ingestArgs += "0"
}
if ($OtelConsole) {
    $ingestArgs += "--otel-console"
}
uv run python @ingestArgs
uv run python -m scripts.ingest_unmapped_blobs --generate-sample --reset-table

$dbtExitCode = 0
Push-Location dbt_transforms
try {
    uv run dbt build --profiles-dir ../dbt_profiles
    $dbtExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($dbtExitCode -ne 0) {
    Write-Warning "dbt reported blockers for the scenario data. Continuing to write triage, promotion review, and versioning artifacts."
}

uv run python -m scripts.triage_quality_failures
uv run python -m scripts.review_gold_promotion

if ($dbtExitCode -eq 0) {
    uv run python -m scripts.generate_dashboard_preview
    uv run python -m scripts.generate_fhir_mapping_workbench
    uv run python -m scripts.generate_privacy_report
}
else {
    Write-Warning "Skipping dashboard and privacy report refresh because dbt blocked gold mart promotion."
}

uv run python -m scripts.version_data_release

if ($dbtExitCode -eq 0) {
    Write-Output "Scenario demo completed without dbt blockers."
}
else {
    Write-Output "Scenario demo completed with expected blockers. Last-known-good pointer was not replaced unless the run met promotion rules."
}
