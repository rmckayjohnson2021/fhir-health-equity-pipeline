param(
    [switch]$TraceMappings,
    [switch]$OtelConsole,
    [ValidateSet("none", "missing_id", "unsupported_resource", "malformed_json")]
    [string]$ChaosScenario = "none",
    [double]$TraceDelaySeconds = 0.05,
    [int]$PatientCount = 60,
    [int]$BatchSize = 20,
    [double]$DelaySeconds = 1.0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$batchArgs = @("-m", "scripts.run_batch_demo")
$batchArgs += "--patient-count"
$batchArgs += $PatientCount.ToString([Globalization.CultureInfo]::InvariantCulture)
$batchArgs += "--batch-size"
$batchArgs += $BatchSize.ToString([Globalization.CultureInfo]::InvariantCulture)
$batchArgs += "--delay-seconds"
$batchArgs += $DelaySeconds.ToString([Globalization.CultureInfo]::InvariantCulture)
if ($TraceMappings) {
    $batchArgs += "--trace-mappings"
    $batchArgs += "--trace-delay-seconds"
    $batchArgs += $TraceDelaySeconds.ToString([Globalization.CultureInfo]::InvariantCulture)
}
if ($OtelConsole) {
    $batchArgs += "--otel-console"
}
if ($ChaosScenario -ne "none") {
    $batchArgs += "--chaos-scenario"
    $batchArgs += $ChaosScenario
}

uv run python @batchArgs
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
