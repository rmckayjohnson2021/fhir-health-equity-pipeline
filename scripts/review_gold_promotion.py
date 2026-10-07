"""Create a decision queue for records blocked from gold promotion."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_QUARANTINE_DIR = Path("data/quarantine")
DEFAULT_TARGET_DIR = Path("dbt_transforms/target")
DEFAULT_REPORT_PATH = Path("reports/gold_promotion_review.md")
DEFAULT_DECISIONS_PATH = Path("reports/gold_promotion_decisions.jsonl")
BLOCKING_TEST_STATUSES = {"fail", "error", "warn"}

DECISION_OPTIONS = {
    "1": ("request_source_correction", "Ask the simulated source owner to fix and resend the record."),
    "2": ("fix_mapping_and_reprocess", "Update the mapping rule, then rerun ingestion and dbt."),
    "3": ("reject_from_gold", "Keep the record out of gold marts and retain audit evidence."),
    "4": ("accept_exception_for_monitoring", "Allow a documented exception only if downstream analytics stay safe."),
    "5": ("defer", "Leave the item in the review queue for later stewardship."),
}

DEFAULT_DECISION_BY_TYPE = {
    "ingestion_quarantine": "request_source_correction",
    "dbt_test_blocker": "fix_mapping_and_reprocess",
}


@dataclass(frozen=True)
class PromotionIssue:
    issue_id: str
    issue_type: str
    source_system: str
    resource_type: str
    resource_id: str
    reason: str
    evidence: str
    recommended_decision: str


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_raw_payload(raw_payload: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def quarantine_issues(quarantine_dir: Path) -> list[PromotionIssue]:
    issues: list[PromotionIssue] = []
    for path in sorted(quarantine_dir.glob("*/quarantine.ndjson")):
        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                payload = parse_raw_payload(row.get("raw_payload", ""))
                source_system = row.get("source_system", "unknown")
                resource_type = payload.get("resourceType", "unknown")
                resource_id = payload.get("id", "missing-id")
                issue_id = f"quarantine-{source_system}-{resource_type}-{line_number}"
                issues.append(
                    PromotionIssue(
                        issue_id=issue_id,
                        issue_type="ingestion_quarantine",
                        source_system=source_system,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        reason=row.get("reason", "unknown quarantine reason"),
                        evidence=f"{row.get('source_file', path)}:{row.get('line_number', line_number)}",
                        recommended_decision=DEFAULT_DECISION_BY_TYPE["ingestion_quarantine"],
                    )
                )
    return issues


def affected_model_name(node: dict[str, Any], manifest: dict[str, Any]) -> str:
    attached_node_id = node.get("attached_node")
    if attached_node_id and attached_node_id in manifest.get("nodes", {}):
        return manifest["nodes"][attached_node_id].get("name", attached_node_id)

    dependencies = node.get("depends_on", {}).get("nodes", [])
    for dependency in dependencies:
        if dependency.startswith("model.") and dependency in manifest.get("nodes", {}):
            return manifest["nodes"][dependency].get("name", dependency)

    return "unknown"


def dbt_blocker_issues(target_dir: Path) -> list[PromotionIssue]:
    run_results = load_json(target_dir / "run_results.json")
    manifest = load_json(target_dir / "manifest.json")
    if not run_results or not manifest:
        return []

    issues: list[PromotionIssue] = []
    for result in run_results.get("results", []):
        unique_id = result.get("unique_id", "")
        if not unique_id.startswith("test.") or result.get("status") not in BLOCKING_TEST_STATUSES:
            continue

        node = manifest.get("nodes", {}).get(unique_id, {})
        test_name = node.get("name", unique_id)
        affected_model = affected_model_name(node, manifest)
        status = result.get("status", "unknown")
        failures = result.get("failures")
        failure_count = "unknown" if failures is None else str(failures)
        issues.append(
            PromotionIssue(
                issue_id=f"dbt-{test_name}",
                issue_type="dbt_test_blocker",
                source_system="modeled_data",
                resource_type=affected_model,
                resource_id="multiple_or_unknown",
                reason=f"dbt test `{test_name}` returned `{status}` with {failure_count} failing rows",
                evidence=unique_id,
                recommended_decision=DEFAULT_DECISION_BY_TYPE["dbt_test_blocker"],
            )
        )
    return issues


def choose_decision(issue: PromotionIssue) -> str:
    print("\nGold promotion decision required")
    print(f"  Issue: {issue.issue_id}")
    print(f"  Source/resource: {issue.source_system} {issue.resource_type}/{issue.resource_id}")
    print(f"  Reason: {issue.reason}")
    print(f"  Evidence: {issue.evidence}")
    print(f"  Recommended: {issue.recommended_decision}")
    for key, (decision, description) in DECISION_OPTIONS.items():
        print(f"  {key}. {decision} - {description}")

    answer = input("Choose a decision [press Enter for recommended]: ").strip()
    if not answer:
        return issue.recommended_decision
    if answer in DECISION_OPTIONS:
        return DECISION_OPTIONS[answer][0]
    print("  Unrecognized choice; using recommended decision.")
    return issue.recommended_decision


def build_decisions(issues: list[PromotionIssue], interactive: bool) -> list[dict[str, Any]]:
    decisions = []
    for issue in issues:
        decision = choose_decision(issue) if interactive else issue.recommended_decision
        decisions.append({**asdict(issue), "decision": decision})
    return decisions


def build_report(decisions: list[dict[str, Any]]) -> str:
    lines = [
        "# Gold Promotion Review",
        "",
        "This report identifies synthetic records or model failures that should not feed gold analytics until a stewardship decision is made.",
        "",
        "Gold promotion means the data is safe enough to appear in dashboard-ready marts. Bronze landing alone is not treated as approval for stakeholder reporting.",
        "",
        "## Summary",
        "",
        f"- Review items: {len(decisions)}",
    ]

    by_decision: dict[str, int] = {}
    for row in decisions:
        by_decision[row["decision"]] = by_decision.get(row["decision"], 0) + 1
    for decision, count in sorted(by_decision.items()):
        lines.append(f"- `{decision}`: {count}")

    lines.extend(["", "## Decision Queue", ""])
    if not decisions:
        lines.extend(["No gold promotion blockers were detected in the latest run.", ""])
        return "\n".join(lines)

    lines.extend(
        [
            "| Issue | Source | Resource | Reason | Decision | Evidence |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in decisions:
        lines.append(
            f"| `{row['issue_id']}` | `{row['source_system']}` | "
            f"`{row['resource_type']}/{row['resource_id']}` | {row['reason']} | "
            f"`{row['decision']}` | `{row['evidence']}` |"
        )

    lines.extend(
        [
            "",
            "## Decision Options",
            "",
            "- `request_source_correction`: the feed record is invalid for promotion and should be corrected upstream before retry.",
            "- `fix_mapping_and_reprocess`: the payload may be valid, but local mapping rules need to change before promotion.",
            "- `reject_from_gold`: the record remains auditable but is excluded from gold marts.",
            "- `accept_exception_for_monitoring`: a documented exception is allowed only when analytics remain safe.",
            "- `defer`: the item stays open for later stewardship.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review records blocked from gold-mart promotion.")
    parser.add_argument("--quarantine-dir", type=Path, default=DEFAULT_QUARANTINE_DIR)
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--decisions-path", type=Path, default=DEFAULT_DECISIONS_PATH)
    parser.add_argument("--interactive", action="store_true", help="Prompt for a decision for each review item.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    issues = quarantine_issues(args.quarantine_dir)
    issues.extend(dbt_blocker_issues(args.target_dir))
    decisions = build_decisions(issues, args.interactive)

    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(build_report(decisions) + "\n", encoding="utf-8")

    args.decisions_path.parent.mkdir(parents=True, exist_ok=True)
    with args.decisions_path.open("w", encoding="utf-8", newline="\n") as file:
        for decision in decisions:
            file.write(json.dumps(decision, sort_keys=True))
            file.write("\n")

    print(f"Wrote gold promotion review to {args.report_path}")
    print(f"Wrote gold promotion decisions to {args.decisions_path}")


if __name__ == "__main__":
    main()
