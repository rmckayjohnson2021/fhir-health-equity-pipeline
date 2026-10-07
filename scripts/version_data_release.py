"""Snapshot a successful local pipeline run as the last known good data release."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb


DEFAULT_DATABASE = Path("data/warehouse/health_equity.duckdb")
DEFAULT_TARGET_DIR = Path("dbt_transforms/target")
DEFAULT_DASHBOARD = Path("dashboards/static_preview.html")
DEFAULT_FHIR_WORKBENCH = Path("dashboards/fhir_mapping_workbench.html")
DEFAULT_TRIAGE_REPORT = Path("reports/data_quality_triage.md")
DEFAULT_PROMOTION_REPORT = Path("reports/gold_promotion_review.md")
DEFAULT_PRIVACY_REPORT = Path("reports/privacy_masking_report.md")
DEFAULT_UNMAPPED_REPORT = Path("reports/unmapped_source_drawer.md")
DEFAULT_VERSION_DIR = Path("data/run_versions")
DEFAULT_SUMMARY_REPORT = Path("reports/last_known_good.md")
DBT_BLOCKING_STATUSES = {"fail", "error", "warn"}


def utc_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def table_exists(connection: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    return bool(
        connection.sql(
            """
            select count(*)
            from information_schema.tables
            where table_schema || '.' || table_name = ?
            """,
            params=[table_name],
        ).fetchone()[0]
    )


def safe_count(connection: duckdb.DuckDBPyConnection, table_name: str) -> int:
    if not table_exists(connection, table_name):
        return 0
    return connection.sql(f"select count(*) from {table_name}").fetchone()[0]


def dbt_summary(target_dir: Path) -> dict[str, Any]:
    run_results = load_json(target_dir / "run_results.json")
    results = run_results.get("results", [])
    blocking_results = [
        result for result in results if result.get("status") in DBT_BLOCKING_STATUSES
    ]
    test_results = [result for result in results if result.get("unique_id", "").startswith("test.")]
    return {
        "total_results": len(results),
        "total_tests": len(test_results),
        "passing_tests": sum(1 for result in test_results if result.get("status") == "pass"),
        "blocking_results": len(blocking_results),
        "is_good": bool(results) and not blocking_results,
    }


def warehouse_summary(database: Path) -> dict[str, Any]:
    if not database.exists():
        return {
            "loaded_resources": 0,
            "quarantined_records": 0,
            "source_systems": 0,
            "diabetes_cohort": 0,
            "warehouse_exists": False,
        }

    with duckdb.connect(str(database), read_only=True) as connection:
        loaded_resources = safe_count(connection, "bronze.raw_fhir_resources")
        if table_exists(connection, "bronze.ingestion_metrics"):
            quarantined_records = connection.sql(
                "select coalesce(sum(records_quarantined), 0) from bronze.ingestion_metrics"
            ).fetchone()[0]
            source_systems = connection.sql(
                "select count(distinct source_system) from bronze.ingestion_metrics"
            ).fetchone()[0]
        else:
            quarantined_records = 0
            source_systems = 0
        diabetes_cohort = safe_count(connection, "main_gold.mart_diabetes_care_gaps")

    return {
        "loaded_resources": loaded_resources,
        "quarantined_records": quarantined_records,
        "source_systems": source_systems,
        "diabetes_cohort": diabetes_cohort,
        "warehouse_exists": True,
    }


def copy_if_exists(source: Path, destination: Path) -> str | None:
    if not source.exists():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return str(destination)


def build_markdown(pointer: dict[str, Any]) -> str:
    status = "Promoted" if pointer["promoted"] else "Not promoted"
    lines = [
        "# Last Known Good Data Release",
        "",
        f"- Status: `{status}`",
        f"- Run id: `{pointer['run_id']}`",
        f"- Recorded at: `{pointer['recorded_at']}`",
        f"- Loaded resources: {pointer['warehouse']['loaded_resources']}",
        f"- Quarantined records: {pointer['warehouse']['quarantined_records']}",
        f"- Source systems: {pointer['warehouse']['source_systems']}",
        f"- Diabetes cohort rows: {pointer['warehouse']['diabetes_cohort']}",
        f"- dbt tests: {pointer['dbt']['passing_tests']}/{pointer['dbt']['total_tests']} passed",
        f"- dbt blocking results: {pointer['dbt']['blocking_results']}",
        "",
        "## Snapshot Contents",
        "",
    ]
    for label, path in pointer["artifacts"].items():
        if path:
            lines.append(f"- `{label}`: `{path}`")
    lines.extend(
        [
            "",
            "This local snapshot is a portfolio demonstration of release governance. It does not contain real patient data.",
            "",
        ]
    )
    return "\n".join(lines)


def record_release(
    database: Path,
    target_dir: Path,
    dashboard: Path,
    fhir_workbench: Path,
    triage_report: Path,
    promotion_report: Path,
    privacy_report: Path,
    unmapped_report: Path,
    version_dir: Path,
    summary_report: Path,
    force: bool,
) -> dict[str, Any]:
    run_id = utc_run_id()
    snapshot_dir = version_dir / run_id
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    dbt = dbt_summary(target_dir)
    warehouse = warehouse_summary(database)
    promoted = bool(force or (dbt["is_good"] and warehouse["warehouse_exists"]))

    artifacts = {
        "warehouse": copy_if_exists(database, snapshot_dir / "warehouse.duckdb"),
        "dbt_run_results": copy_if_exists(target_dir / "run_results.json", snapshot_dir / "dbt_run_results.json"),
        "dbt_manifest": copy_if_exists(target_dir / "manifest.json", snapshot_dir / "dbt_manifest.json"),
        "dashboard": copy_if_exists(dashboard, snapshot_dir / "static_preview.html"),
        "fhir_workbench": copy_if_exists(fhir_workbench, snapshot_dir / "fhir_mapping_workbench.html"),
        "triage_report": copy_if_exists(triage_report, snapshot_dir / "data_quality_triage.md"),
        "promotion_report": copy_if_exists(promotion_report, snapshot_dir / "gold_promotion_review.md"),
        "privacy_report": copy_if_exists(privacy_report, snapshot_dir / "privacy_masking_report.md"),
        "unmapped_report": copy_if_exists(unmapped_report, snapshot_dir / "unmapped_source_drawer.md"),
    }

    pointer = {
        "run_id": run_id,
        "recorded_at": datetime.now(UTC).isoformat(),
        "promoted": promoted,
        "promotion_reason": "forced" if force else "dbt passed and warehouse exists",
        "snapshot_dir": str(snapshot_dir),
        "dbt": dbt,
        "warehouse": warehouse,
        "artifacts": artifacts,
    }

    manifest_path = snapshot_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    version_dir.mkdir(parents=True, exist_ok=True)
    registry_path = version_dir / "run_registry.jsonl"
    with registry_path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(pointer, sort_keys=True))
        file.write("\n")

    if promoted:
        (version_dir / "last_known_good.json").write_text(
            json.dumps(pointer, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        summary_report.parent.mkdir(parents=True, exist_ok=True)
        summary_report.write_text(build_markdown(pointer), encoding="utf-8", newline="\n")

    return pointer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Version a successful local pipeline run as last known good.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR)
    parser.add_argument("--dashboard", type=Path, default=DEFAULT_DASHBOARD)
    parser.add_argument("--fhir-workbench", type=Path, default=DEFAULT_FHIR_WORKBENCH)
    parser.add_argument("--triage-report", type=Path, default=DEFAULT_TRIAGE_REPORT)
    parser.add_argument("--promotion-report", type=Path, default=DEFAULT_PROMOTION_REPORT)
    parser.add_argument("--privacy-report", type=Path, default=DEFAULT_PRIVACY_REPORT)
    parser.add_argument("--unmapped-report", type=Path, default=DEFAULT_UNMAPPED_REPORT)
    parser.add_argument("--version-dir", type=Path, default=DEFAULT_VERSION_DIR)
    parser.add_argument("--summary-report", type=Path, default=DEFAULT_SUMMARY_REPORT)
    parser.add_argument("--force", action="store_true", help="Record this run as last known good even with blockers.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pointer = record_release(
        args.database,
        args.target_dir,
        args.dashboard,
        args.fhir_workbench,
        args.triage_report,
        args.promotion_report,
        args.privacy_report,
        args.unmapped_report,
        args.version_dir,
        args.summary_report,
        args.force,
    )
    status = "promoted to last known good" if pointer["promoted"] else "recorded but not promoted"
    print(f"Run {pointer['run_id']} {status}.")
    print(f"Snapshot: {pointer['snapshot_dir']}")


if __name__ == "__main__":
    main()
