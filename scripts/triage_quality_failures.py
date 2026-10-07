"""Create a Markdown triage report from dbt test artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb


DEFAULT_TARGET_DIR = Path("dbt_transforms/target")
DEFAULT_OUTPUT_PATH = Path("reports/data_quality_triage.md")
DEFAULT_DATABASE = Path("data/warehouse/health_equity.duckdb")
FAILURE_STATUSES = {"fail", "error", "warn"}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Expected dbt artifact not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def infer_likely_cause(test_name: str, status: str) -> str:
    normalized = test_name.lower()

    if status == "error":
        return "The test could not execute, which often points to SQL, dependency, or schema drift."
    if "relationships" in normalized:
        return "A child record references a parent key that is missing from the modeled patient set."
    if "not_null" in normalized:
        return "A required field is missing after ingestion or normalization."
    if "unique" in normalized:
        return "The model has duplicate business keys and may need deduplication rules."
    if "accepted_values" in normalized:
        return "A source value appeared outside the governed value set."
    if "a1c" in normalized:
        return "An A1c result is outside the clinically plausible range configured for the demo."

    return "The test failed and needs model-specific investigation."


def infer_next_step(test_name: str, affected_model: str) -> str:
    normalized = test_name.lower()

    if "relationships" in normalized:
        return f"Compare `{affected_model}` patient references against `stg_fhir_patients` and inspect source-system routing."
    if "not_null" in normalized:
        return f"Inspect raw FHIR payloads feeding `{affected_model}` and decide whether to backfill, quarantine, or relax the field requirement."
    if "unique" in normalized:
        return f"Check whether `{affected_model}` needs source-system namespacing, latest-record filtering, or duplicate quarantine."
    if "accepted_values" in normalized:
        return f"Review the unexpected values in `{affected_model}` and update either source mapping or governed value sets."
    if "a1c" in normalized:
        return "Inspect A1c units and values; A1c should be represented as percent or mmol/mol, not mg/dL."

    return f"Open the compiled dbt SQL for `{affected_model}` and inspect failing rows."


def affected_model_name(node: dict[str, Any], manifest: dict[str, Any]) -> str:
    attached_node_id = node.get("attached_node")
    if attached_node_id and attached_node_id in manifest.get("nodes", {}):
        return manifest["nodes"][attached_node_id].get("name", attached_node_id)

    dependencies = node.get("depends_on", {}).get("nodes", [])
    for dependency in dependencies:
        if dependency.startswith("model.") and dependency in manifest.get("nodes", {}):
            return manifest["nodes"][dependency].get("name", dependency)

    return "unknown"


def test_display_name(node: dict[str, Any]) -> str:
    metadata = node.get("test_metadata") or {}
    if metadata.get("name"):
        return metadata["name"]
    return node.get("name", node.get("unique_id", "unknown_test"))


def quarantine_summary(database: Path) -> list[tuple[str, str, int, int, int]]:
    if not database.exists():
        return []

    with duckdb.connect(str(database), read_only=True) as connection:
        return connection.sql(
            """
            select
                source_system,
                resource_type,
                records_seen,
                records_loaded,
                records_quarantined
            from bronze.ingestion_metrics
            where records_quarantined > 0
            order by source_system, resource_type
            """
        ).fetchall()


def build_report(run_results: dict[str, Any], manifest: dict[str, Any], database: Path) -> str:
    results = run_results.get("results", [])
    test_results = [result for result in results if result.get("unique_id", "").startswith("test.")]
    failing_results = [result for result in test_results if result.get("status") in FAILURE_STATUSES]
    quarantined_results = quarantine_summary(database)

    lines = [
        "# Data Quality Triage Report",
        "",
        "This report is generated from dbt artifacts after the local demo build.",
        "",
        "## Summary",
        "",
        f"- Total dbt test results: {len(test_results)}",
        f"- Failing or warning tests: {len(failing_results)}",
        f"- Source/resource groups with quarantined records: {len(quarantined_results)}",
        "",
    ]

    lines.extend(["## Ingestion Quarantine", ""])
    if quarantined_results:
        lines.extend(
            [
                "| Source system | Resource type | Seen | Loaded | Quarantined | Suggested next step |",
                "|---|---:|---:|---:|---:|---|",
            ]
        )
        for source_system, resource_type, seen, loaded, quarantined in quarantined_results:
            lines.append(
                f"| `{source_system}` | `{resource_type}` | {seen} | {loaded} | {quarantined} | "
                "Inspect the quarantine NDJSON and decide whether to correct the source mapping or reject the feed record. |"
            )
        lines.append("")
    else:
        lines.extend(["No records were quarantined during ingestion.", ""])

    if not failing_results:
        lines.extend(
            [
                "## Findings",
                "",
                "No failing dbt tests were detected in the latest run.",
                "",
                "This does not prove the data is production-ready. It means the current synthetic fixture passed the v1 checks for identity, referential integrity, accepted values, and clinical plausibility.",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(["## Findings", ""])
    for result in failing_results:
        unique_id = result.get("unique_id", "")
        node = manifest.get("nodes", {}).get(unique_id, {})
        test_name = test_display_name(node)
        affected_model = affected_model_name(node, manifest)
        status = result.get("status", "unknown")
        failures = result.get("failures")
        failure_count = "unknown" if failures is None else str(failures)

        lines.extend(
            [
                f"### {test_name}",
                "",
                f"- Status: `{status}`",
                f"- Affected model: `{affected_model}`",
                f"- Failure count: `{failure_count}`",
                f"- Likely cause: {infer_likely_cause(test_name, status)}",
                f"- Suggested next step: {infer_next_step(test_name, affected_model)}",
                "",
            ]
        )

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a Markdown data quality triage report from dbt artifacts.")
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_results = load_json(args.target_dir / "run_results.json")
    manifest = load_json(args.target_dir / "manifest.json")
    report = build_report(run_results, manifest, args.database)

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(report + "\n", encoding="utf-8")
    print(f"Wrote data quality triage report to {args.output_path}")


if __name__ == "__main__":
    main()
