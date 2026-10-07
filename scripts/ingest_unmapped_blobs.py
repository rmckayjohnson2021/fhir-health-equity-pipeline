"""Store unmapped synthetic source blobs for provenance and future semantic mapping."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from scripts.ingest_fhir import DEFAULT_DATABASE


DEFAULT_INPUT_DIR = Path("data/unmapped_source")
DEFAULT_OUTPUT_DIR = Path("data/generated/unmapped_source")
DEFAULT_REPORT_PATH = Path("reports/unmapped_source_drawer.md")
SIMULATED_SOURCE_SYSTEMS = ("epic_simulated", "athena_simulated", "legacy_pms_simulated")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def ensure_schema(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        create schema if not exists bronze;

        create table if not exists bronze.unmapped_source_blobs (
            blob_id varchar not null,
            source_system varchar not null,
            source_file varchar not null,
            content_type varchar not null,
            content_hash varchar not null,
            received_at timestamp not null,
            mapping_status varchar not null,
            semantic_hint varchar,
            raw_blob varchar not null
        );
        """
    )


def synthetic_blobs() -> list[tuple[str, str, str, str]]:
    return [
        (
            "epic_simulated",
            "care-manager-note-001.txt",
            "text/plain",
            "Patient reports food insecurity and prefers evening outreach. Contains narrative context not mapped to v1 FHIR resources.",
        ),
        (
            "athena_simulated",
            "referral-fax-001.txt",
            "text/plain",
            "Scanned referral summary: transportation barrier noted; diabetes follow-up requested. Needs document parsing before semantic mapping.",
        ),
        (
            "legacy_pms_simulated",
            "screening-export-001.json",
            "application/json",
            json.dumps(
                {
                    "screening_tool": "local_sdh_screen",
                    "housing_status_text": "temporarily staying with family",
                    "food_access_text": "sometimes runs out before month end",
                    "mapping_note": "Candidate for future Observation or QuestionnaireResponse mapping.",
                },
                sort_keys=True,
            ),
        ),
    ]


def generate_sample_blobs(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    for source_system, filename, _content_type, content in synthetic_blobs():
        path = output_dir / source_system / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def content_type_for(path: Path) -> str:
    if path.suffix.lower() == ".json":
        return "application/json"
    if path.suffix.lower() in {".txt", ".text"}:
        return "text/plain"
    return "application/octet-stream"


def semantic_hint_for(blob: str) -> str:
    normalized = blob.lower()
    hints = []
    if "food" in normalized:
        hints.append("food_insecurity")
    if "transport" in normalized:
        hints.append("transportation_barrier")
    if "housing" in normalized:
        hints.append("housing_instability")
    if "referral" in normalized:
        hints.append("referral_document")
    return ",".join(hints) if hints else "needs_review"


def iter_blob_files(input_dir: Path) -> list[Path]:
    return sorted(path for path in input_dir.glob("*/*") if path.is_file())


def ingest_blobs(input_dir: Path, database: Path, reset_table: bool) -> dict[str, int]:
    rows = []
    for path in iter_blob_files(input_dir):
        raw_blob = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(raw_blob.encode("utf-8")).hexdigest()
        source_system = path.parent.name
        blob_id = f"blob-{digest[:12]}"
        rows.append(
            (
                blob_id,
                source_system,
                str(path),
                content_type_for(path),
                digest,
                utc_now(),
                "unmapped_retained",
                semantic_hint_for(raw_blob),
                raw_blob,
            )
        )

    database.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database)) as connection:
        ensure_schema(connection)
        if reset_table:
            connection.execute("delete from bronze.unmapped_source_blobs")
        if rows:
            connection.executemany(
                """
                insert into bronze.unmapped_source_blobs
                    (blob_id, source_system, source_file, content_type, content_hash, received_at,
                     mapping_status, semantic_hint, raw_blob)
                values (?, ?, ?, ?, ?, cast(? as timestamp), ?, ?, ?)
                """,
                rows,
            )

    return {"files": len(rows)}


def report_rows(database: Path) -> list[tuple[Any, ...]]:
    if not database.exists():
        return []
    with duckdb.connect(str(database), read_only=True) as connection:
        return connection.sql(
            """
            select
                blob_id,
                source_system,
                content_type,
                mapping_status,
                semantic_hint,
                left(content_hash, 12) as hash_prefix,
                source_file
            from bronze.unmapped_source_blobs
            order by received_at, blob_id
            """
        ).fetchall()


def write_report(database: Path, output_path: Path) -> None:
    rows = report_rows(database)
    lines = [
        "# Unmapped Source Drawer",
        "",
        "This report lists synthetic source blobs that could not be mapped into the v1 FHIR resource set. They are retained for provenance and future semantic mapping, but excluded from gold analytics.",
        "",
        f"- Retained blobs: {len(rows)}",
        "",
        "| Blob | Source | Content type | Status | Semantic hint | Hash prefix | Source file |",
        "|---|---|---|---|---|---|---|",
    ]
    for blob_id, source_system, content_type, status, hint, hash_prefix, source_file in rows:
        lines.append(
            f"| `{blob_id}` | `{source_system}` | `{content_type}` | `{status}` | "
            f"`{hint}` | `{hash_prefix}` | `{source_file}` |"
        )
    lines.extend(
        [
            "",
            "The drawer preserves lineage without treating unmodeled blobs as analytics-ready facts.",
            "",
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest unmapped synthetic source blobs into a provenance drawer.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--generate-sample", action="store_true", help="Generate sample unmapped source blobs first.")
    parser.add_argument("--reset-table", action="store_true", help="Clear existing unmapped blob rows before ingesting.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.generate_sample:
        generate_sample_blobs(args.input_dir)
    summary = ingest_blobs(args.input_dir, args.database, reset_table=args.reset_table)
    write_report(args.database, args.report_path)
    print(f"Ingested {summary['files']} unmapped source blobs.")
    print(f"Wrote unmapped source drawer report to {args.report_path}")


if __name__ == "__main__":
    main()
