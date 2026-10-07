"""Generate larger synthetic FHIR scenario data for resilience demos."""

from __future__ import annotations

import argparse
import json
import random
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from scripts.generate_synthea_sample import (
    SOURCE_SYSTEMS,
    SyntheticPatient,
    appointment_resource,
    communication_resource,
    diabetes_condition_resource,
    encounter_resource,
    patient_resource,
)


DEFAULT_OUTPUT_DIR = Path("data/scenario_raw")
FIRST_NAMES = ("Ana", "Marcus", "Mireille", "Elena", "Andre", "Samira", "Luis", "Grace", "Noah", "Iris")
LAST_NAMES = ("Rivera", "Johnson", "Jean", "Patel", "Williams", "Nguyen", "Brown", "Garcia", "Ali", "Thomas")
LANGUAGES = (
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("ht", "Haitian Creole"),
    ("ar", "Arabic"),
)
POSTAL_CODES = ("60608", "60619", "60644", "60623", "60629", "60632", "60651", "60612")
SCENARIOS = (
    "clean",
    "stale_a1c",
    "missing_a1c",
    "missing_phone",
    "missing_language",
    "missing_postal_code",
    "duplicate_patient_id",
    "unsupported_resource",
    "missing_resource_id",
    "malformed_json",
    "implausible_a1c",
    "wrong_a1c_unit",
)


def scenario_for_index(index: int) -> str:
    if index % 53 == 0:
        return "malformed_json"
    if index % 47 == 0:
        return "unsupported_resource"
    if index % 43 == 0:
        return "missing_resource_id"
    if index % 37 == 0:
        return "wrong_a1c_unit"
    if index % 31 == 0:
        return "implausible_a1c"
    if index % 29 == 0:
        return "duplicate_patient_id"
    if index % 19 == 0:
        return "missing_language"
    if index % 17 == 0:
        return "missing_postal_code"
    if index % 11 == 0:
        return "missing_phone"
    if index % 7 == 0:
        return "missing_a1c"
    if index % 5 == 0:
        return "stale_a1c"
    return "clean"


def synthetic_patient(index: int, scenario: str) -> SyntheticPatient:
    source_system = SOURCE_SYSTEMS[index % len(SOURCE_SYSTEMS)]
    first_name = FIRST_NAMES[index % len(FIRST_NAMES)]
    last_name = LAST_NAMES[(index * 3) % len(LAST_NAMES)]
    language_code, language_display = LANGUAGES[(index * 2) % len(LANGUAGES)]
    birth_year = 1948 + (index % 52)
    birth_month = 1 + (index % 12)
    birth_day = 1 + (index % 27)
    patient_id = f"patient-{index:05d}"
    if scenario == "duplicate_patient_id" and index > 1:
        patient_id = f"patient-{index - 1:05d}"

    a1c_value = round(5.6 + ((index * 7) % 42) / 10, 1)
    last_a1c_date = f"2026-{1 + (index % 3):02d}-{1 + (index % 27):02d}"
    if scenario == "stale_a1c":
        last_a1c_date = f"2024-{1 + (index % 12):02d}-{1 + (index % 27):02d}"
    elif scenario == "missing_a1c":
        a1c_value = None
        last_a1c_date = None
    elif scenario == "implausible_a1c":
        a1c_value = 42.0
    elif scenario == "wrong_a1c_unit":
        a1c_value = 165.0

    return SyntheticPatient(
        patient_id=patient_id,
        source_system=source_system,
        family_name=last_name,
        given_name=first_name,
        gender="female" if index % 2 else "male",
        birth_date=f"{birth_year}-{birth_month:02d}-{birth_day:02d}",
        language_code=language_code,
        language_display=language_display,
        postal_code=POSTAL_CODES[index % len(POSTAL_CODES)],
        phone=None if scenario == "missing_phone" else f"555-{1000 + index:04d}",
        a1c_value=a1c_value,
        last_a1c_date=last_a1c_date,
    )


def a1c_observation(patient: SyntheticPatient, scenario: str) -> dict[str, Any] | None:
    if patient.a1c_value is None or patient.last_a1c_date is None:
        return None

    unit = "mg/dL" if scenario == "wrong_a1c_unit" else "%"
    return {
        "resourceType": "Observation",
        "id": f"observation-a1c-{patient.patient_id[-5:]}",
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "4548-4",
                    "display": "Hemoglobin A1c/Hemoglobin.total in Blood",
                }
            ],
            "text": "Hemoglobin A1c",
        },
        "subject": {"reference": f"Patient/{patient.patient_id}"},
        "effectiveDateTime": patient.last_a1c_date,
        "valueQuantity": {
            "value": patient.a1c_value,
            "unit": unit,
            "system": "http://unitsofmeasure.org",
            "code": unit,
        },
    }


def unsupported_resource(patient: SyntheticPatient) -> dict[str, Any]:
    return {
        "resourceType": "MedicationRequest",
        "id": f"medication-request-{patient.patient_id[-5:]}",
        "status": "active",
        "subject": {"reference": f"Patient/{patient.patient_id}"},
        "fixture_note": "Synthetic unsupported resource type.",
    }


def missing_id_observation(patient: SyntheticPatient) -> dict[str, Any]:
    return {
        "resourceType": "Observation",
        "status": "final",
        "code": {"text": "Hemoglobin A1c"},
        "subject": {"reference": f"Patient/{patient.patient_id}"},
        "valueQuantity": {"value": 7.2, "unit": "%"},
        "fixture_note": "Synthetic missing id.",
    }


def resources_for_scenario(patient: SyntheticPatient, scenario: str) -> list[dict[str, Any]]:
    patient_payload = patient_resource(patient)
    if scenario == "missing_language":
        patient_payload.pop("communication", None)
    if scenario == "missing_postal_code":
        patient_payload["address"] = [{}]

    records = [
        patient_payload,
        encounter_resource(patient),
        diabetes_condition_resource(patient),
        appointment_resource(patient),
        communication_resource(patient),
    ]
    observation = a1c_observation(patient, scenario)
    if observation:
        records.append(observation)
    if scenario == "unsupported_resource":
        records.append(unsupported_resource(patient))
    if scenario == "missing_resource_id":
        records.append(missing_id_observation(patient))
    return records


def write_source_file(path: Path, records: list[dict[str, Any]], malformed_lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, sort_keys=True))
            file.write("\n")
        for line in malformed_lines:
            file.write(line)
            file.write("\n")


def generate_scenario_data(output_dir: Path, patient_count: int, seed: int, clean: bool) -> dict[str, Any]:
    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    random.seed(seed)
    records_by_source: dict[str, list[dict[str, Any]]] = {source: [] for source in SOURCE_SYSTEMS}
    malformed_by_source: dict[str, list[str]] = {source: [] for source in SOURCE_SYSTEMS}
    scenario_counts = {scenario: 0 for scenario in SCENARIOS}

    for index in range(1, patient_count + 1):
        scenario = scenario_for_index(index)
        patient = synthetic_patient(index, scenario)
        scenario_counts[scenario] += 1
        records_by_source[patient.source_system].extend(resources_for_scenario(patient, scenario))
        if scenario == "malformed_json":
            malformed_by_source[patient.source_system].append(
                '{"resourceType": "Observation", "id": "malformed-scenario-record", "status": "final"'
            )

    for source_system, records in records_by_source.items():
        write_source_file(output_dir / source_system / "fhir.ndjson", records, malformed_by_source[source_system])

    manifest = {
        "description": "Larger deterministic synthetic FHIR scenario data. No real patient data.",
        "patient_count": patient_count,
        "seed": seed,
        "source_systems": list(SOURCE_SYSTEMS),
        "scenario_counts": {key: value for key, value in scenario_counts.items() if value},
    }
    (output_dir / "scenario_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate larger synthetic FHIR scenario data.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--patient-count", type=int, default=250)
    parser.add_argument("--seed", type=int, default=20261007)
    parser.add_argument("--no-clean", action="store_true", help="Append/overwrite files without removing the output directory first.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = generate_scenario_data(args.output_dir, args.patient_count, args.seed, clean=not args.no_clean)
    print(f"Generated {manifest['patient_count']} synthetic scenario patients under {args.output_dir}")
    print("Scenario counts:")
    for scenario, count in manifest["scenario_counts"].items():
        print(f"  - {scenario}: {count}")


if __name__ == "__main__":
    main()
