"""Simulate micro-batch FHIR ingestion for the local pipeline demo."""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

import duckdb

from scripts.generate_synthea_sample import (
    DEFAULT_PATIENT_COUNT,
    SOURCE_SYSTEMS,
    SyntheticPatient,
    invalid_fixture,
    patient_panel,
    resources_for_patient,
    write_ndjson,
)
from scripts.ingest_fhir import DEFAULT_DATABASE, DEFAULT_QUARANTINE_DIR, clean_outputs, ingest
from scripts.observability import configure_console_tracing, start_span


DEFAULT_BATCH_DIR = Path("data/batches")
CHAOS_SCENARIOS = ("none", "missing_id", "unsupported_resource", "malformed_json")


def unsupported_resource_fixture() -> dict[str, object]:
    return {
        "resourceType": "MedicationRequest",
        "id": "chaos-medication-request-001",
        "status": "active",
        "subject": {"reference": "Patient/patient-003"},
        "fixture_note": "Intentional chaos record: unsupported resource type for quarantine demo.",
    }


def write_batch(
    batch_dir: Path,
    batch_number: int,
    patients: list[SyntheticPatient],
    include_invalid: bool = False,
    chaos_scenario: str = "none",
) -> Path:
    batch_path = batch_dir / f"batch_{batch_number:03d}"
    if batch_path.exists():
        shutil.rmtree(batch_path)

    for source_system in SOURCE_SYSTEMS:
        records = []
        for patient in patients:
            if patient.source_system == source_system:
                records.extend(resources_for_patient(patient))

        if include_invalid and source_system == "legacy_pms_simulated":
            records.append(invalid_fixture())

        if batch_number == 3 and source_system == "legacy_pms_simulated":
            if chaos_scenario == "missing_id":
                records.append(invalid_fixture())
            elif chaos_scenario == "unsupported_resource":
                records.append(unsupported_resource_fixture())

        if records:
            write_ndjson(batch_path / source_system / "fhir.ndjson", records)

            if batch_number == 3 and source_system == "legacy_pms_simulated" and chaos_scenario == "malformed_json":
                with (batch_path / source_system / "fhir.ndjson").open("a", encoding="utf-8", newline="\n") as file:
                    file.write('{"resourceType": "Observation", "id": "chaos-malformed-001"\n')

    return batch_path


def print_operational_summary(database: Path) -> None:
    with duckdb.connect(str(database), read_only=True) as connection:
        loaded = connection.sql("select count(*) from bronze.raw_fhir_resources").fetchone()[0]
        quarantined = connection.sql(
            "select coalesce(sum(records_quarantined), 0) from bronze.ingestion_metrics"
        ).fetchone()[0]
        source_summary = connection.sql(
            """
            select
                source_system,
                sum(records_seen) as seen,
                sum(records_loaded) as loaded,
                sum(records_quarantined) as quarantined
            from bronze.ingestion_metrics
            group by 1
            order by 1
            """
        ).fetchall()

    print(f"  Cumulative loaded resources: {loaded}")
    print(f"  Cumulative quarantined records: {quarantined}")
    for source_system, seen, source_loaded, source_quarantined in source_summary:
        print(f"  - {source_system}: seen={seen}, loaded={source_loaded}, quarantined={source_quarantined}")


def run_batches(
    batch_dir: Path,
    database: Path,
    quarantine_dir: Path,
    patient_count: int,
    batch_size: int,
    delay_seconds: float,
    trace_mappings: bool,
    trace_delay_seconds: float,
    chaos_scenario: str,
    tracer: object | None,
) -> None:
    if batch_dir.exists():
        shutil.rmtree(batch_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)

    clean_outputs(database, quarantine_dir)

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    patients = list(patient_panel(patient_count))
    batches = [patients[index : index + batch_size] for index in range(0, len(patients), batch_size)]

    for batch_number, batch_patients in enumerate(batches, start=1):
        is_final_batch = batch_number == len(batches)
        batch_chaos_scenario = chaos_scenario if is_final_batch else "none"
        with start_span(
            tracer,
            "synthetic_batch.process",
            {
                "batch.number": batch_number,
                "batch.total": len(batches),
                "batch.patient_count": len(batch_patients),
                "batch.chaos_scenario": batch_chaos_scenario,
            },
        ) as batch_span:
            batch_path = write_batch(
                batch_dir,
                batch_number,
                batch_patients,
                is_final_batch,
                batch_chaos_scenario,
            )
            print(f"\nProcessing batch {batch_number}/{len(batches)}: {batch_path}")
            print(f"  Synthetic patients in batch: {len(batch_patients)}")
            if batch_chaos_scenario != "none":
                print(f"  Chaos injector enabled: {batch_chaos_scenario}")
                batch_span.add_event("chaos.injected", {"chaos.scenario": batch_chaos_scenario})

            summary = ingest(
                batch_path,
                database,
                quarantine_dir,
                reset_tables=False,
                trace_mappings=trace_mappings,
                trace_delay_seconds=trace_delay_seconds,
                tracer=tracer,
            )
            batch_span.set_attribute("records.seen", summary["seen"])
            batch_span.set_attribute("records.loaded", summary["loaded"])
            batch_span.set_attribute("records.quarantined", summary["quarantined"])
            print(
                "  Batch result: "
                f"{summary['loaded']} loaded, {summary['quarantined']} quarantined, "
                f"{summary['seen']} seen across {summary['files']} files."
            )
            print_operational_summary(database)

        if delay_seconds > 0 and batch_number != len(batches):
            time.sleep(delay_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulate near-real-time synthetic FHIR micro-batch ingestion.")
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH_DIR)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--quarantine-dir", type=Path, default=DEFAULT_QUARANTINE_DIR)
    parser.add_argument("--patient-count", type=int, default=DEFAULT_PATIENT_COUNT)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    parser.add_argument("--trace-mappings", action="store_true", help="Print live FHIR-to-model mapping traces.")
    parser.add_argument("--otel-console", action="store_true", help="Emit OpenTelemetry spans to stdout.")
    parser.add_argument(
        "--chaos-scenario",
        choices=CHAOS_SCENARIOS,
        default="none",
        help="Inject one synthetic bad event into the third batch.",
    )
    parser.add_argument(
        "--trace-delay-seconds",
        type=float,
        default=0.05,
        help="Optional pause after each mapping trace record so the stream is easier to watch.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tracer = configure_console_tracing(args.otel_console, "fhir-health-equity-pipeline")
    with start_span(tracer, "synthetic_batch_demo.run", {"chaos.scenario": args.chaos_scenario}):
        run_batches(
            args.batch_dir,
            args.database,
            args.quarantine_dir,
            args.patient_count,
            args.batch_size,
            args.delay_seconds,
            args.trace_mappings,
            args.trace_delay_seconds,
            args.chaos_scenario,
            tracer,
        )
    print("\nBatch ingestion complete. Run dbt build to refresh downstream marts.")


if __name__ == "__main__":
    main()
