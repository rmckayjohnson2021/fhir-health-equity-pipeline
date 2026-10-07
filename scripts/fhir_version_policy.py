"""Persist a local demo policy for FHIR version and forced mapping decisions."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_PATH = ROOT / "data" / "work" / "fhir_version_policy.json"
DEFAULT_REPORT_PATH = ROOT / "reports" / "fhir_version_policy.md"
VALID_FHIR_VERSIONS = ("R4", "R4B", "R5")
VALID_POLICY_MODES = ("simulate", "apply_forward")


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_policy() -> dict[str, Any]:
    return {
        "active_version": "R4",
        "mode": "simulate",
        "effective_at": None,
        "policy_status": "default_demo_policy",
        "scope": "simulation_only",
        "previous_runs_immutable": True,
        "backfill_required_for_history": True,
        "forced_mappings": [],
        "history": [],
    }


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    if not path.exists():
        return default_policy()
    return json.loads(path.read_text(encoding="utf-8"))


def save_policy(policy: dict[str, Any], path: Path = DEFAULT_POLICY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_forced_mappings(values: list[str | dict[str, Any]] | None) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for value in values or []:
        if isinstance(value, dict):
            field = str(value.get("field", "")).strip()
            target_type = str(value.get("target_type", "")).strip()
        else:
            if "=" not in value:
                raise ValueError(f"Forced mapping must use field=target_type format: {value}")
            field, target_type = [part.strip() for part in value.split("=", 1)]
        if not field or not target_type:
            raise ValueError("Forced mapping requires both field and target_type.")
        normalized.append({"field": field, "target_type": target_type})
    return normalized


def record_policy(
    *,
    version: str,
    mode: str,
    effective_at: str | None,
    note: str,
    forced_mappings: list[str | dict[str, Any]] | None = None,
    path: Path = DEFAULT_POLICY_PATH,
) -> dict[str, Any]:
    if version not in VALID_FHIR_VERSIONS:
        raise ValueError(f"Unsupported FHIR version: {version}")
    if mode not in VALID_POLICY_MODES:
        raise ValueError(f"Unsupported policy mode: {mode}")

    policy = load_policy(path)
    recorded_at = now_iso()
    entry = {
        "id": f"policy-{recorded_at.replace(':', '').replace('-', '')}",
        "recorded_at": recorded_at,
        "previous_version": policy.get("active_version", "R4"),
        "selected_version": version,
        "mode": mode,
        "effective_at": effective_at or recorded_at,
        "scope": "from_effective_timestamp_forward" if mode == "apply_forward" else "simulation_only",
        "previous_runs_unchanged": True,
        "backfill_required_for_history": True,
        "note": note.strip() or "No note supplied.",
        "forced_mappings": normalize_forced_mappings(forced_mappings),
    }

    policy["active_version"] = version
    policy["mode"] = mode
    policy["effective_at"] = entry["effective_at"]
    policy["policy_status"] = "recorded_demo_policy"
    policy["scope"] = entry["scope"]
    policy["previous_runs_immutable"] = True
    policy["backfill_required_for_history"] = True
    policy["forced_mappings"] = entry["forced_mappings"]
    policy.setdefault("history", []).append(entry)
    save_policy(policy, path)
    return policy


def revert_policy(
    *,
    effective_at: str | None,
    note: str,
    path: Path = DEFAULT_POLICY_PATH,
) -> dict[str, Any]:
    policy = load_policy(path)
    history = policy.get("history", [])
    target_version = history[-1].get("previous_version", "R4") if history else "R4"
    revert_note = note.strip() or f"Reverted future loads to {target_version}."
    updated = record_policy(
        version=target_version,
        mode="apply_forward",
        effective_at=effective_at,
        note=revert_note,
        forced_mappings=[],
        path=path,
    )
    updated["history"][-1]["revert_of"] = history[-1]["id"] if history else None
    save_policy(updated, path)
    return updated


def build_report(policy: dict[str, Any]) -> str:
    history = policy.get("history", [])
    lines = [
        "# FHIR Version Policy",
        "",
        "This local demo artifact records FHIR version and forced mapping decisions made from the mapping workbench.",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Active version | {policy.get('active_version', 'R4')} |",
        f"| Mode | {policy.get('mode', 'simulate')} |",
        f"| Effective at | {policy.get('effective_at') or 'Not applied'} |",
        f"| Scope | {policy.get('scope', 'simulation_only')} |",
        f"| Previous runs immutable | {policy.get('previous_runs_immutable', True)} |",
        f"| Backfill required for history | {policy.get('backfill_required_for_history', True)} |",
        "",
        "Previous pipeline runs are treated as immutable evidence. A version migration applies only from the selected timestamp forward unless an explicit replay/backfill is run.",
        "",
        "## Current Forced Mappings",
        "",
    ]

    forced_mappings = policy.get("forced_mappings", [])
    if forced_mappings:
        lines.extend(["| Source field | Forced FHIR target type |", "| --- | --- |"])
        for mapping in forced_mappings:
            lines.append(f"| {mapping['field']} | {mapping['target_type']} |")
    else:
        lines.append("No active forced mappings.")

    lines.extend(["", "## Decision History", ""])
    if history:
        lines.append("| Recorded at | Previous | Selected | Mode | Effective at | Note |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for entry in reversed(history[-10:]):
            note = str(entry.get("note", "")).replace("|", "/")
            lines.append(
                f"| {entry.get('recorded_at')} | {entry.get('previous_version')} | "
                f"{entry.get('selected_version')} | {entry.get('mode')} | "
                f"{entry.get('effective_at')} | {note} |"
            )
    else:
        lines.append("No migration decisions have been recorded yet.")

    lines.extend(["", "Generated from `scripts/fhir_version_policy.py` using synthetic data only.", ""])
    return "\n".join(lines)


def write_report(policy: dict[str, Any], output_path: Path = DEFAULT_REPORT_PATH) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_report(policy), encoding="utf-8", newline="\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record or report local FHIR version policy decisions.")
    parser.add_argument("--version", choices=VALID_FHIR_VERSIONS, default="R4")
    parser.add_argument("--mode", choices=VALID_POLICY_MODES, default="simulate")
    parser.add_argument("--effective-at")
    parser.add_argument("--note", default="")
    parser.add_argument("--forced-mapping", action="append", default=[])
    parser.add_argument("--revert", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.report_only:
        policy = load_policy()
    elif args.revert:
        policy = revert_policy(effective_at=args.effective_at, note=args.note)
    else:
        policy = record_policy(
            version=args.version,
            mode=args.mode,
            effective_at=args.effective_at,
            note=args.note,
            forced_mappings=args.forced_mapping,
        )
    write_report(policy)
    print(f"Wrote FHIR version policy report to {DEFAULT_REPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
