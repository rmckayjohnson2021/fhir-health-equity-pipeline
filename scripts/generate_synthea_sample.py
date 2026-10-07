"""Generate a tiny deterministic synthetic FHIR sample for the local demo.

This is a lightweight v1 fixture that keeps the repo runnable without Java,
Synthea, cloud services, or real patient data. The records are FHIR-shaped
synthetic examples and can be replaced by exported Synthea NDJSON later.
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = Path("data/raw")
DEFAULT_PATIENT_COUNT = 60
SOURCE_SYSTEMS = ("epic_simulated", "athena_simulated", "legacy_pms_simulated")
FIRST_NAMES = ("Ana", "Marcus", "Mireille", "Elena", "Andre", "Samira", "Luis", "Grace", "Noah", "Iris")
LAST_NAMES = ("Rivera", "Johnson", "Jean", "Patel", "Williams", "Nguyen", "Brown", "Garcia", "Ali", "Thomas")
LANGUAGES = (
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("ht", "Haitian Creole"),
    ("ar", "Arabic"),
)
LANGUAGE_SEQUENCE = (
    ("en", "English"),
    ("es", "Spanish"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("ht", "Haitian Creole"),
    ("ar", "Arabic"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
)
POSTAL_CODES = ("60608", "60619", "60644", "60623", "60629", "60632", "60651", "60612")


@dataclass(frozen=True)
class SyntheticPatient:
    patient_id: str
    source_system: str
    family_name: str
    given_name: str
    gender: str
    birth_date: str
    language_code: str
    language_display: str
    postal_code: str
    phone: str | None
    a1c_value: float | None
    last_a1c_date: str | None


PATIENTS = (
    SyntheticPatient(
        patient_id="patient-001",
        source_system="epic_simulated",
        family_name="Rivera",
        given_name="Ana",
        gender="female",
        birth_date="1978-04-12",
        language_code="es",
        language_display="Spanish",
        postal_code="60608",
        phone="555-0101",
        a1c_value=8.2,
        last_a1c_date="2026-02-15",
    ),
    SyntheticPatient(
        patient_id="patient-002",
        source_system="athena_simulated",
        family_name="Johnson",
        given_name="Marcus",
        gender="male",
        birth_date="1966-11-30",
        language_code="en",
        language_display="English",
        postal_code="60619",
        phone="555-0102",
        a1c_value=None,
        last_a1c_date=None,
    ),
    SyntheticPatient(
        patient_id="patient-003",
        source_system="legacy_pms_simulated",
        family_name="Jean",
        given_name="Mireille",
        gender="female",
        birth_date="1984-08-21",
        language_code="ht",
        language_display="Haitian Creole",
        postal_code="60644",
        phone=None,
        a1c_value=6.9,
        last_a1c_date="2025-09-01",
    ),
)


def generated_patient(index: int, variation_seed: int = 0) -> SyntheticPatient:
    source_system = SOURCE_SYSTEMS[(index - 1) % len(SOURCE_SYSTEMS)]
    first_name = FIRST_NAMES[(index - 1) % len(FIRST_NAMES)]
    last_name = LAST_NAMES[((index - 1) * 3) % len(LAST_NAMES)]
    language_code, language_display = LANGUAGE_SEQUENCE[(index - 1) % len(LANGUAGE_SEQUENCE)]
    clinical_index = index + variation_seed
    age_cycle = (24, 29, 34, 38, 43, 49, 56, 62, 67, 73, 79)
    age_years = age_cycle[(index - 1) % len(age_cycle)]
    birth_year = date.today().year - age_years
    birth_month = 1 + (index % 12)
    birth_day = 1 + (index % 27)

    if clinical_index % 5 == 0:
        a1c_value = None
        last_a1c_date = None
    else:
        a1c_value = round(5.8 + ((clinical_index * 7) % 36) / 10, 1)
        last_a1c_date = (
            f"2024-{1 + (clinical_index % 12):02d}-{1 + (clinical_index % 27):02d}"
            if clinical_index % 4 == 0
            else f"2026-{1 + (clinical_index % 5):02d}-{1 + (clinical_index % 27):02d}"
        )

    return SyntheticPatient(
        patient_id=f"patient-{index:03d}",
        source_system=source_system,
        family_name=last_name,
        given_name=first_name,
        gender="female" if index % 2 else "male",
        birth_date=f"{birth_year}-{birth_month:02d}-{birth_day:02d}",
        language_code=language_code,
        language_display=language_display,
        postal_code=POSTAL_CODES[(index - 1) % len(POSTAL_CODES)],
        phone=None if index % 8 == 0 else f"555-{1000 + index:04d}",
        a1c_value=a1c_value,
        last_a1c_date=last_a1c_date,
    )


def patient_panel(patient_count: int, variation_seed: int = 0) -> tuple[SyntheticPatient, ...]:
    if patient_count < len(PATIENTS):
        raise ValueError(f"patient_count must be at least {len(PATIENTS)}")

    patients = list(PATIENTS)
    for index in range(len(PATIENTS) + 1, patient_count + 1):
        patients.append(generated_patient(index, variation_seed))
    return tuple(patients)


def patient_resource(patient: SyntheticPatient) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "resourceType": "Patient",
        "id": patient.patient_id,
        "name": [{"family": patient.family_name, "given": [patient.given_name]}],
        "gender": patient.gender,
        "birthDate": patient.birth_date,
        "address": [{"postalCode": patient.postal_code}],
        "communication": [
            {
                "language": {
                    "coding": [
                        {
                            "system": "urn:ietf:bcp:47",
                            "code": patient.language_code,
                            "display": patient.language_display,
                        }
                    ],
                    "text": patient.language_display,
                },
                "preferred": True,
            }
        ],
    }
    if patient.phone:
        resource["telecom"] = [{"system": "phone", "value": patient.phone, "use": "mobile"}]
    return resource


def encounter_resource(patient: SyntheticPatient) -> dict[str, Any]:
    return {
        "resourceType": "Encounter",
        "id": f"encounter-{patient.patient_id[-3:]}",
        "status": "finished",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"},
        "subject": {"reference": f"Patient/{patient.patient_id}"},
        "period": {"start": "2026-01-10T09:00:00-06:00", "end": "2026-01-10T09:30:00-06:00"},
    }


def diabetes_condition_resource(patient: SyntheticPatient) -> dict[str, Any]:
    return {
        "resourceType": "Condition",
        "id": f"condition-diabetes-{patient.patient_id[-3:]}",
        "clinicalStatus": {
            "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]
        },
        "code": {
            "coding": [{"system": "http://snomed.info/sct", "code": "44054006", "display": "Diabetes mellitus type 2"}],
            "text": "Diabetes mellitus type 2",
        },
        "subject": {"reference": f"Patient/{patient.patient_id}"},
        "onsetDateTime": "2020-01-01",
    }


def a1c_observation_resource(patient: SyntheticPatient) -> dict[str, Any] | None:
    if patient.a1c_value is None or patient.last_a1c_date is None:
        return None

    return {
        "resourceType": "Observation",
        "id": f"observation-a1c-{patient.patient_id[-3:]}",
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
        "valueQuantity": {"value": patient.a1c_value, "unit": "%", "system": "http://unitsofmeasure.org", "code": "%"},
    }


def appointment_resource(patient: SyntheticPatient) -> dict[str, Any]:
    return {
        "resourceType": "Appointment",
        "id": f"appointment-{patient.patient_id[-3:]}",
        "status": "booked",
        "start": "2026-04-15T10:00:00-05:00",
        "participant": [{"actor": {"reference": f"Patient/{patient.patient_id}"}, "status": "accepted"}],
    }


def communication_resource(patient: SyntheticPatient) -> dict[str, Any]:
    channel = "sms" if patient.phone else "mail"
    return {
        "resourceType": "Communication",
        "id": f"communication-{patient.patient_id[-3:]}",
        "status": "completed",
        "subject": {"reference": f"Patient/{patient.patient_id}"},
        "sent": "2026-03-01T12:00:00-06:00",
        "medium": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ParticipationMode", "code": channel}]}],
    }


def resources_for_patient(patient: SyntheticPatient) -> list[dict[str, Any]]:
    resources = [
        patient_resource(patient),
        encounter_resource(patient),
        diabetes_condition_resource(patient),
        appointment_resource(patient),
        communication_resource(patient),
    ]
    observation = a1c_observation_resource(patient)
    if observation:
        resources.append(observation)
    return resources


def invalid_fixture() -> dict[str, Any]:
    return {
        "resourceType": "Observation",
        "status": "final",
        "code": {"text": "Hemoglobin A1c"},
        "subject": {"reference": "Patient/patient-999"},
        "valueQuantity": {"value": 42.0, "unit": "%"},
        "fixture_note": "Intentional invalid record: missing id for quarantine demo.",
    }


def write_ndjson(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, sort_keys=True))
            file.write("\n")


def generate_sample(output_dir: Path, patient_count: int = DEFAULT_PATIENT_COUNT, variation_seed: int = 0) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)

    patients = patient_panel(patient_count, variation_seed)
    for source_system in SOURCE_SYSTEMS:
        source_records: list[dict[str, Any]] = []
        for patient in patients:
            if patient.source_system == source_system:
                source_records.extend(resources_for_patient(patient))

        if source_system == "legacy_pms_simulated":
            source_records.append(invalid_fixture())

        write_ndjson(output_dir / source_system / "fhir.ndjson", source_records)

    manifest = {
        "description": "Deterministic synthetic FHIR-shaped v1 fixture. No real patient data.",
        "source_systems": list(SOURCE_SYSTEMS),
        "patients": len(patients),
        "variation_seed": variation_seed,
        "intentional_invalid_records": 1,
    }
    write_ndjson(output_dir / "_manifest.ndjson", [manifest])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic FHIR NDJSON sample data.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--patient-count", type=int, default=DEFAULT_PATIENT_COUNT)
    parser.add_argument("--variation-seed", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate_sample(args.output_dir, args.patient_count, args.variation_seed)
    print(f"Generated synthetic FHIR sample under {args.output_dir}")


if __name__ == "__main__":
    main()
