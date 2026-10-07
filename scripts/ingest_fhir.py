"""Route synthetic FHIR NDJSON into DuckDB bronze tables."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from scripts.observability import configure_console_tracing, mark_error, start_span


DEFAULT_INPUT_DIR = Path("data/raw")
DEFAULT_DATABASE = Path("data/warehouse/health_equity.duckdb")
DEFAULT_QUARANTINE_DIR = Path("data/quarantine")

ACCEPTED_SOURCE_SYSTEMS = {"epic_simulated", "athena_simulated", "legacy_pms_simulated"}
ACCEPTED_RESOURCE_TYPES = {"Patient", "Encounter", "Condition", "Observation", "Appointment", "Communication"}

FHIR_MAPPING_TRACE: dict[str, tuple[str, tuple[tuple[str, str], ...]]] = {
    "Patient": (
        "stg_fhir_patients",
        (
            ("$.id", "patient_id"),
            ("$.name[0].family", "family_name"),
            ("$.name[0].given[0]", "given_name"),
            ("$.gender", "gender"),
            ("$.birthDate", "birth_date"),
            ("$.communication[0].language.coding[0].code", "preferred_language_code"),
            ("$.address[0].postalCode", "postal_code"),
            ("$.telecom[0].value", "phone"),
        ),
    ),
    "Encounter": (
        "stg_fhir_encounters",
        (
            ("$.id", "encounter_id"),
            ("$.subject.reference", "patient_id"),
            ("$.status", "encounter_status"),
            ("$.class.code", "encounter_class"),
            ("$.period.start", "encounter_start_at"),
            ("$.period.end", "encounter_end_at"),
        ),
    ),
    "Condition": (
        "stg_fhir_conditions",
        (
            ("$.id", "condition_id"),
            ("$.subject.reference", "patient_id"),
            ("$.code.coding[0].code", "condition_code"),
            ("$.code.text", "condition_name"),
            ("$.clinicalStatus.coding[0].code", "clinical_status"),
            ("$.onsetDateTime", "onset_date"),
        ),
    ),
    "Observation": (
        "stg_fhir_observations",
        (
            ("$.id", "observation_id"),
            ("$.subject.reference", "patient_id"),
            ("$.status", "observation_status"),
            ("$.code.coding[0].code", "observation_code"),
            ("$.code.text", "observation_name"),
            ("$.effectiveDateTime", "effective_date"),
            ("$.valueQuantity.value", "value_quantity"),
            ("$.valueQuantity.unit", "value_unit"),
        ),
    ),
    "Appointment": (
        "stg_fhir_appointments",
        (
            ("$.id", "appointment_id"),
            ("$.participant[0].actor.reference", "patient_id"),
            ("$.status", "appointment_status"),
            ("$.start", "appointment_start_at"),
        ),
    ),
    "Communication": (
        "stg_fhir_communications",
        (
            ("$.id", "communication_id"),
            ("$.subject.reference", "patient_id"),
            ("$.status", "communication_status"),
            ("$.medium[0].coding[0].code", "communication_channel"),
            ("$.sent", "sent_at"),
        ),
    ),
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def clean_outputs(database: Path, quarantine_dir: Path) -> None:
    if database.exists():
        database.unlink()
    wal_path = database.with_suffix(database.suffix + ".wal")
    if wal_path.exists():
        wal_path.unlink()
    if quarantine_dir.exists():
        shutil.rmtree(quarantine_dir)


def ensure_schema(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        create schema if not exists bronze;

        create table if not exists bronze.raw_fhir_resources (
            source_system varchar not null,
            resource_type varchar not null,
            resource_id varchar not null,
            ingested_at timestamp not null,
            source_file varchar not null,
            raw_json varchar not null
        );

        create table if not exists bronze.ingestion_metrics (
            source_system varchar not null,
            resource_type varchar not null,
            records_seen integer not null,
            records_loaded integer not null,
            records_quarantined integer not null,
            processed_at timestamp not null
        );
        """
    )


def validate_record(record: Any, source_system: str) -> str | None:
    if source_system not in ACCEPTED_SOURCE_SYSTEMS:
        return f"unknown source_system {source_system}"
    if not isinstance(record, dict):
        return "payload is not a JSON object"

    resource_type = record.get("resourceType")
    if resource_type not in ACCEPTED_RESOURCE_TYPES:
        return f"unsupported resourceType {resource_type!r}"
    if not record.get("id"):
        return "missing required FHIR resource id"

    return None


def iter_source_files(input_dir: Path) -> list[Path]:
    return sorted(path for path in input_dir.glob("*/*.ndjson") if path.is_file())


def write_quarantine_record(quarantine_dir: Path, quarantine_record: dict[str, Any]) -> None:
    source_system = quarantine_record["source_system"]
    output_path = quarantine_dir / source_system / "quarantine.ndjson"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(quarantine_record, sort_keys=True))
        file.write("\n")


def extract_json_path(record: dict[str, Any], json_path: str) -> Any:
    current: Any = record
    for token in json_path.removeprefix("$.").split("."):
        key = token
        index: int | None = None
        if "[" in token and token.endswith("]"):
            key, index_text = token[:-1].split("[", 1)
            index = int(index_text)

        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]

        if index is not None:
            if not isinstance(current, list) or index >= len(current):
                return None
            current = current[index]

    return current


def normalize_trace_value(json_path: str, value: Any) -> Any:
    if isinstance(value, str) and json_path.endswith(".reference") and value.startswith("Patient/"):
        return value.replace("Patient/", "")
    return value


def emit_mapping_trace(
    source_system: str,
    source_file: Path,
    line_number: int,
    record: dict[str, Any] | None,
    resource_type: str,
    status: str,
    reason: str | None,
    delay_seconds: float,
) -> None:
    resource_id = record.get("id") if isinstance(record, dict) else None
    label = f"{resource_type}/{resource_id or 'missing-id'}"
    print(f"[mapping-trace] {status} {source_system} {label}", flush=True)
    print(f"  source: {source_file}:{line_number}", flush=True)

    if reason:
        print(f"  quarantine_reason: {reason}", flush=True)
    elif isinstance(record, dict):
        model_name, mappings = FHIR_MAPPING_TRACE.get(resource_type, ("bronze.raw_fhir_resources", ()))
        print(f"  target: bronze.raw_fhir_resources -> {model_name}", flush=True)
        for json_path, column_name in mappings:
            raw_value = extract_json_path(record, json_path)
            mapped_value = normalize_trace_value(json_path, raw_value)
            print(f"  map: {json_path} -> {column_name} = {mapped_value!r}", flush=True)

    if delay_seconds > 0:
        time.sleep(delay_seconds)


def ingest(
    input_dir: Path,
    database: Path,
    quarantine_dir: Path,
    reset_tables: bool = True,
    trace_mappings: bool = False,
    trace_delay_seconds: float = 0.0,
    tracer: Any | None = None,
) -> dict[str, int]:
    database.parent.mkdir(parents=True, exist_ok=True)
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    loaded_rows: list[tuple[str, str, str, str, str, str]] = []
    seen_counts: Counter[tuple[str, str]] = Counter()
    loaded_counts: Counter[tuple[str, str]] = Counter()
    quarantined_counts: Counter[tuple[str, str]] = Counter()

    for source_file in iter_source_files(input_dir):
        source_system = source_file.parent.name

        with start_span(
            tracer,
            "fhir.source_file",
            {"source.system": source_system, "source.file": str(source_file)},
        ) as file_span:
            with source_file.open("r", encoding="utf-8") as file:
                for line_number, line in enumerate(file, start=1):
                    raw_line = line.strip()
                    if not raw_line:
                        continue

                    json_error: json.JSONDecodeError | None = None
                    try:
                        record = json.loads(raw_line)
                    except json.JSONDecodeError as error:
                        json_error = error
                        record = None
                        reason = f"invalid JSON: {error.msg}"
                        resource_type = "unknown"
                    else:
                        reason = validate_record(record, source_system)
                        resource_type = record.get("resourceType", "unknown") if isinstance(record, dict) else "unknown"

                    resource_id = record.get("id") if isinstance(record, dict) else None
                    with start_span(
                        tracer,
                        "fhir.resource.validate",
                        {
                            "source.system": source_system,
                            "source.file": str(source_file),
                            "source.line": line_number,
                            "fhir.resource_type": resource_type,
                            "fhir.resource_id": resource_id or "missing-id",
                        },
                    ) as resource_span:
                        seen_counts[(source_system, resource_type)] += 1

                        if reason:
                            quarantined_counts[(source_system, resource_type)] += 1
                            resource_span.set_attribute("pipeline.outcome", "quarantined")
                            resource_span.set_attribute("quarantine.reason", reason)
                            resource_span.add_event("fhir.resource.quarantined", {"quarantine.reason": reason})
                            file_span.add_event(
                                "fhir.resource.quarantined",
                                {
                                    "fhir.resource_type": resource_type,
                                    "quarantine.reason": reason,
                                },
                            )
                            mark_error(resource_span, reason, json_error)
                            if trace_mappings:
                                emit_mapping_trace(
                                    source_system,
                                    source_file,
                                    line_number,
                                    record if isinstance(record, dict) else None,
                                    resource_type,
                                    "QUARANTINE",
                                    reason,
                                    trace_delay_seconds,
                                )
                            write_quarantine_record(
                                quarantine_dir,
                                {
                                    "source_system": source_system,
                                    "source_file": str(source_file),
                                    "line_number": line_number,
                                    "reason": reason,
                                    "raw_payload": raw_line,
                                    "quarantined_at": utc_now(),
                                },
                            )
                            continue

                        loaded_counts[(source_system, resource_type)] += 1
                        resource_span.set_attribute("pipeline.outcome", "loaded")
                        resource_span.add_event("fhir.resource.loaded")
                        if trace_mappings:
                            emit_mapping_trace(
                                source_system,
                                source_file,
                                line_number,
                                record,
                                resource_type,
                                "LOAD",
                                None,
                                trace_delay_seconds,
                            )
                        loaded_rows.append(
                            (
                                source_system,
                                resource_type,
                                record["id"],
                                utc_now(),
                                str(source_file),
                                json.dumps(record, sort_keys=True),
                            )
                        )

    with duckdb.connect(str(database)) as connection:
        ensure_schema(connection)
        if reset_tables:
            connection.execute("delete from bronze.raw_fhir_resources")
            connection.execute("delete from bronze.ingestion_metrics")

        if loaded_rows:
            connection.executemany(
                """
                insert into bronze.raw_fhir_resources
                    (source_system, resource_type, resource_id, ingested_at, source_file, raw_json)
                values (?, ?, ?, cast(? as timestamp), ?, ?)
                """,
                loaded_rows,
            )

        metric_rows = []
        processed_at = utc_now()
        for source_system, resource_type in sorted(seen_counts):
            metric_rows.append(
                (
                    source_system,
                    resource_type,
                    seen_counts[(source_system, resource_type)],
                    loaded_counts[(source_system, resource_type)],
                    quarantined_counts[(source_system, resource_type)],
                    processed_at,
                )
            )

        if metric_rows:
            connection.executemany(
                """
                insert into bronze.ingestion_metrics
                    (source_system, resource_type, records_seen, records_loaded, records_quarantined, processed_at)
                values (?, ?, ?, ?, ?, cast(? as timestamp))
                """,
                metric_rows,
            )

    return {
        "files": len(iter_source_files(input_dir)),
        "seen": sum(seen_counts.values()),
        "loaded": len(loaded_rows),
        "quarantined": sum(quarantined_counts.values()),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest synthetic FHIR NDJSON into local DuckDB bronze tables.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--quarantine-dir", type=Path, default=DEFAULT_QUARANTINE_DIR)
    parser.add_argument("--clean-only", action="store_true", help="Remove generated DuckDB and quarantine outputs.")
    parser.add_argument("--trace-mappings", action="store_true", help="Print live FHIR-to-model mapping traces.")
    parser.add_argument("--otel-console", action="store_true", help="Emit OpenTelemetry spans to stdout.")
    parser.add_argument(
        "--trace-delay-seconds",
        type=float,
        default=0.0,
        help="Optional pause after each mapping trace record so the stream is easier to watch.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    clean_outputs(args.database, args.quarantine_dir)
    if args.clean_only:
        print("Removed generated DuckDB and quarantine outputs.")
        return

    summary = ingest(
        args.input_dir,
        args.database,
        args.quarantine_dir,
        trace_mappings=args.trace_mappings,
        trace_delay_seconds=args.trace_delay_seconds,
        tracer=configure_console_tracing(args.otel_console, "fhir-health-equity-pipeline"),
    )
    print(
        "Ingested synthetic FHIR records: "
        f"{summary['loaded']} loaded, {summary['quarantined']} quarantined, "
        f"{summary['seen']} seen across {summary['files']} files."
    )
    print(f"DuckDB: {args.database}")
    print(f"Quarantine: {args.quarantine_dir}")


if __name__ == "__main__":
    main()
