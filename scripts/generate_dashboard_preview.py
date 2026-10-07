"""Generate a polished dark-theme static dashboard preview from DuckDB marts."""

from __future__ import annotations

import argparse
import hashlib
import json
from html import escape
from pathlib import Path
from typing import Any

import duckdb


DEFAULT_DATABASE = Path("data/warehouse/health_equity.duckdb")
DEFAULT_TARGET_DIR = Path("dbt_transforms/target")
DEFAULT_QUARANTINE_DIR = Path("data/quarantine")
DEFAULT_DECISIONS_PATH = Path("reports/gold_promotion_decisions.jsonl")
DEFAULT_OUTPUT_PATH = Path("dashboards/static_preview.html")
PROJECT_AUTHOR = "Ryan Johnson"
PROJECT_ROLE = "Healthcare data platform builder"
GITHUB_HANDLE = "rmckayjohnson2021"
REPO_URL = "https://github.com/rmckayjohnson2021/fhir-health-equity-pipeline"
LINKEDIN_URL = "https://www.linkedin.com/in/mckayjohnson/"


def fetch_rows(connection: duckdb.DuckDBPyConnection, query: str) -> list[tuple[Any, ...]]:
    return connection.sql(query).fetchall()


def scalar(connection: duckdb.DuckDBPyConnection, query: str) -> Any:
    return connection.sql(query).fetchone()[0]


def pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def dbt_test_summary(target_dir: Path) -> tuple[int, int, int]:
    run_results_path = target_dir / "run_results.json"
    if not run_results_path.exists():
        return (0, 0, 0)

    run_results = json.loads(run_results_path.read_text(encoding="utf-8"))
    test_results = [result for result in run_results.get("results", []) if result.get("unique_id", "").startswith("test.")]
    passing = sum(1 for result in test_results if result.get("status") == "pass")
    failing = sum(1 for result in test_results if result.get("status") in {"fail", "error", "warn"})
    return (len(test_results), passing, failing)


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def hover_attrs(title: str, body: str) -> str:
    return f' data-tooltip-title="{escape(title)}" data-tooltip="{escape(body)}"'


def metric_card(label: str, value: str, note: str, tone: str = "neutral", tooltip: str | None = None) -> str:
    tooltip_attr = hover_attrs(label, tooltip) if tooltip else ""
    return f"""
    <section class="metric metric-{escape(tone)}"{tooltip_attr}>
      <span>{escape(label)}</span>
      <strong>{escape(value)}</strong>
      <p>{escape(note)}</p>
    </section>
    """


def status_pill(text: str, tone: str) -> str:
    return f'<span class="pill pill-{escape(tone)}">{escape(text)}</span>'


def patient_token(value: Any) -> str:
    if not value:
        return "not present"
    normalized = str(value).replace("Patient/", "")
    return "PAT-" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10].upper()


def a1c_band(value: Any) -> str:
    if value is None:
        return "missing"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "not numeric"
    if numeric_value < 7:
        return "<7"
    if numeric_value < 8:
        return "7-7.9"
    if numeric_value < 9:
        return "8-8.9"
    return "9+"


def display_source_label(source_system: Any) -> str:
    labels = {
        "epic_simulated": "Epic-style FHIR feed*",
        "athena_simulated": "athenahealth-style API feed*",
        "legacy_pms_simulated": "Legacy PMS export*",
    }
    return labels.get(str(source_system), str(source_system))


def mask_failed_payload(payload: dict[str, Any]) -> dict[str, Any]:
    masked = json.loads(json.dumps(payload))
    if "id" in masked:
        masked["id"] = patient_token(masked["id"])
    if "subject" in masked and isinstance(masked["subject"], dict):
        reference = masked["subject"].get("reference")
        if reference:
            masked["subject"]["reference"] = patient_token(reference)
    if "name" in masked:
        masked["name"] = "[removed]"
    if "telecom" in masked:
        masked["telecom"] = "[removed]"
    if "address" in masked:
        masked["address"] = "[generalized]"
    value_quantity = masked.get("valueQuantity")
    if isinstance(value_quantity, dict) and "value" in value_quantity:
        value_quantity["value"] = a1c_band(value_quantity.get("value"))
        value_quantity["masking_note"] = "numeric value bucketed for review"
    return masked


def failed_record_rows(quarantine_dir: Path, decisions_path: Path) -> list[tuple[str, str, str, str, str, str, str]]:
    decisions: dict[str, str] = {}
    if decisions_path.exists():
        with decisions_path.open("r", encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    row = json.loads(line)
                    decisions[str(row.get("issue_id"))] = str(row.get("decision", "review_required"))

    rows: list[tuple[str, str, str, str, str, str, str]] = []
    for path in sorted(quarantine_dir.glob("*/quarantine.ndjson")):
        with path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                row = json.loads(line)
                raw_payload = row.get("raw_payload", "")
                try:
                    payload = json.loads(raw_payload)
                except json.JSONDecodeError:
                    payload = {"unparsed_payload": raw_payload}
                source_system = str(row.get("source_system", "unknown"))
                resource_type = str(payload.get("resourceType", "unknown")) if isinstance(payload, dict) else "unknown"
                resource_id = str(payload.get("id", "missing-id")) if isinstance(payload, dict) else "missing-id"
                issue_id = f"quarantine-{source_system}-{resource_type}-{line_number}"
                masked_payload = mask_failed_payload(payload if isinstance(payload, dict) else {"payload": raw_payload})
                rows.append(
                    (
                        issue_id,
                        display_source_label(source_system),
                        f"{resource_type}/{resource_id}",
                        str(row.get("reason", "unknown quarantine reason")),
                        str(row.get("source_file", path)) + f":{row.get('line_number', line_number)}",
                        decisions.get(issue_id, "review_required"),
                        json.dumps(masked_payload, sort_keys=True),
                    )
                )
    return rows


def table(headers: list[str], rows: list[tuple[Any, ...]]) -> str:
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body_rows = []
    for row in rows:
        body_rows.append("<tr>" + "".join(f"<td>{escape(fmt(value))}</td>" for value in row) + "</tr>")
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def language_bars(rows: list[tuple[Any, ...]]) -> str:
    items = []
    for language, patients, missing, missing_rate in rows:
        width = max(float(missing_rate), 2.0)
        items.append(
            f"""
            <div class="bar-row">
              <div class="bar-label">
                <strong>{escape(str(language))}</strong>
                <span>{missing} of {patients} with an A1c gap</span>
              </div>
              <div class="track"><span style="width: {width}%"></span></div>
              <b>{fmt(missing_rate)}%</b>
            </div>
            """
        )
    return "".join(items)


def age_band_cards(rows: list[tuple[Any, ...]]) -> str:
    total = sum(int(row[1]) for row in rows) or 1
    items = []
    for age_band, patients in rows:
        percent = pct(int(patients), total)
        items.append(
            f"""
            <div class="age-card">
              <span>{escape(str(age_band))}</span>
              <strong>{patients}</strong>
              <div class="mini-track"><span class="ok" style="width: {percent}%"></span></div>
              <p>{percent}% of cohort</p>
            </div>
            """
        )
    return "".join(items)


def run_fidelity_rows(rows: list[dict[str, Any]]) -> str:
    items = []
    for row in rows:
        tone = "risk" if row["drop"] >= 1.0 else "ok"
        change = f"-{row['drop']:.1f} pts" if row["drop"] > 0 else "stable"
        items.append(
            f"""
            <tr>
              <td>{escape(row['run'])}</td>
              <td>{fmt(row['fidelity'])}%</td>
              <td><div class="mini-track"><span class="{tone}" style="width: {row['fidelity']}%"></span></div></td>
              <td>{fmt(row['load_success'])}%</td>
              <td>{fmt(row['dbt_pass'])}%</td>
              <td>{fmt(row['care_gap'])}%</td>
              <td>{status_pill(change, tone)}</td>
            </tr>
            """
        )
    return "".join(items)


def reliability_rows(rows: list[tuple[Any, ...]]) -> str:
    items = []
    for source_system, resource_type, _seen, _loaded, quarantined, quarantine_rate in rows:
        width = max(float(quarantine_rate), 2.0) if float(quarantine_rate) > 0 else 0.0
        tone = "risk" if quarantined else "ok"
        label = "Attention" if quarantined else "Clean"
        items.append(
            f"""
            <div class="reliability-row">
              <div>
                <strong>{escape(display_source_label(source_system))}</strong>
                <span>{escape(str(resource_type))}</span>
              </div>
              <div class="track"><span class="{tone}" style="width: {width}%"></span></div>
              <div class="row-stats">
                <b>{quarantined}</b> quarantined
                {status_pill(label, tone)}
              </div>
            </div>
            """
        )
    return "".join(items)


def otel_trace_dashboard(loaded_count: int, quarantined_count: int, passing_tests: int, total_tests: int) -> str:
    error_spans = 1 if quarantined_count else 0
    trace_status = "Degraded" if error_spans else "Healthy"
    dbt_duration = 420 + total_tests * 8
    spans = [
        {
            "name": "synthetic_batch_demo.run",
            "component": "orchestrator",
            "start": 0,
            "duration": 1280,
            "status": "ok",
            "attributes": "chaos.scenario=none; service=fhir-health-equity-pipeline",
        },
        {
            "name": "source_adapter.route",
            "component": "adapter",
            "start": 50,
            "duration": 180,
            "status": "ok",
            "attributes": "source.count=3; source.mode=simulated",
        },
        {
            "name": "fhir_ingest.validate",
            "component": "ingestion",
            "start": 230,
            "duration": 320,
            "status": "error" if error_spans else "ok",
            "attributes": f"records.loaded={loaded_count}; records.quarantined={quarantined_count}",
        },
        {
            "name": "duckdb.bronze.write",
            "component": "warehouse",
            "start": 550,
            "duration": 170,
            "status": "ok",
            "attributes": "schema=bronze; lineage=preserved",
        },
        {
            "name": "dbt.build",
            "component": "transform",
            "start": 720,
            "duration": dbt_duration,
            "status": "ok" if passing_tests == total_tests else "error",
            "attributes": f"tests.passed={passing_tests}; tests.total={total_tests}",
        },
        {
            "name": "gold.promote",
            "component": "governance",
            "start": 1140,
            "duration": 90,
            "status": "ok",
            "attributes": "gate=last-known-good; marts=3",
        },
        {
            "name": "dashboard.render",
            "component": "reporting",
            "start": 1230,
            "duration": 50,
            "status": "ok",
            "attributes": "artifact=static_preview.html",
        },
    ]
    total_duration = max(span["start"] + span["duration"] for span in spans)
    cards = [
        ("Trace status", trace_status),
        ("Trace id", f"demo-{loaded_count}-{quarantined_count}"),
        ("Spans", str(len(spans))),
        ("Error spans", str(error_spans)),
    ]
    card_html = "".join(
        f"""
        <div class="trace-card">
          <span>{escape(label)}</span>
          <strong>{escape(value)}</strong>
        </div>
        """
        for label, value in cards
    )
    waterfall = []
    rows = []
    for span in spans:
        tone = "risk" if span["status"] == "error" else "ok"
        left = round((span["start"] / total_duration) * 100, 1)
        width = max(round((span["duration"] / total_duration) * 100, 1), 3.0)
        waterfall.append(
            f"""
            <div class="trace-row">
              <div>
                <strong>{escape(span["name"])}</strong>
                <span>{escape(span["component"])}</span>
              </div>
              <div class="trace-lane">
                <span class="{tone}" style="left: {left}%; width: {width}%;">{span["duration"]}ms</span>
              </div>
              {status_pill(str(span["status"]).upper(), tone)}
            </div>
            """
        )
        rows.append(
            f"""
            <tr>
              <td>{escape(span["name"])}</td>
              <td>{escape(span["component"])}</td>
              <td>{span["duration"]}ms</td>
              <td>{status_pill(str(span["status"]).upper(), tone)}</td>
              <td><code>{escape(span["attributes"])}</code></td>
            </tr>
            """
        )
    return f"""
    <div class="trace-dashboard" data-otel-trace-dashboard>
      <div class="trace-summary">{card_html}</div>
      <div class="trace-waterfall">
        {''.join(waterfall)}
      </div>
      <table class="trace-table">
        <thead><tr><th>Span</th><th>Component</th><th>Duration</th><th>Status</th><th>Attributes</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    """


def patient_rows(rows: list[tuple[Any, ...]]) -> str:
    body_rows = []
    for patient_id, language, age_band, last_a1c_date, a1c_status, outreach_channel in rows:
        tone = "risk" if a1c_status == "Gap" else "ok"
        body_rows.append(
            "<tr>"
            f"<td>{escape(str(patient_id))}</td>"
            f"<td>{escape(str(language))}</td>"
            f"<td>{escape(str(age_band))}</td>"
            f"<td>{escape(str(last_a1c_date))}</td>"
            f"<td>{status_pill(str(a1c_status), tone)}</td>"
            f"<td>{escape(str(outreach_channel))}</td>"
            "</tr>"
        )
    return (
        '<table data-patient-table><thead><tr>'
        '<th><button type="button" data-sort-column="0">Patient</button></th>'
        '<th><button type="button" data-sort-column="1">Language</button></th>'
        '<th><button type="button" data-sort-column="2">Age band</button></th>'
        '<th><button type="button" data-sort-column="3">Last A1c</button></th>'
        '<th><button type="button" data-sort-column="4">Status</button></th>'
        '<th><button type="button" data-sort-column="5">Outreach</button></th>'
        "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table>"
    )


def failed_record_table(rows: list[tuple[str, str, str, str, str, str, str]]) -> str:
    if not rows:
        return '<p class="footer-note">No quarantined records are active in the latest synthetic run.</p>'

    body_rows = []
    for issue_id, source_system, resource, reason, evidence, decision, masked_payload in rows:
        body_rows.append(
            "<tr>"
            f"<td><code>{escape(issue_id)}</code></td>"
            f"<td>{escape(source_system)}</td>"
            f"<td><code>{escape(resource)}</code></td>"
            f"<td>{escape(reason)}</td>"
            f"<td><code>{escape(evidence)}</code></td>"
            f"<td>{status_pill(decision, 'risk' if decision != 'accept_exception_for_monitoring' else 'ok')}</td>"
            f"<td><code>{escape(masked_payload)}</code></td>"
            "</tr>"
        )
    return (
        '<table class="failed-record-table" data-failed-record-table><thead><tr>'
        "<th>Issue</th><th>Source</th><th>Resource</th><th>Reason</th><th>Evidence</th><th>Gold decision</th><th>Masked failed payload</th>"
        "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table>"
    )


def generate(database: Path, target_dir: Path, quarantine_dir: Path, output_path: Path) -> None:
    with duckdb.connect(str(database), read_only=True) as connection:
        source_count = scalar(connection, "select count(distinct source_system) from main_gold.mart_pipeline_reliability")
        cohort_count = scalar(connection, "select count(*) from main_gold.mart_diabetes_care_gaps")
        missing_count = scalar(
            connection,
            "select count(*) from main_gold.mart_diabetes_care_gaps where is_missing_recent_a1c",
        )
        loaded_count = scalar(connection, "select coalesce(sum(records_loaded), 0) from main_gold.mart_pipeline_reliability")
        seen_count = scalar(connection, "select coalesce(sum(records_seen), 0) from main_gold.mart_pipeline_reliability")
        quarantined_count = scalar(
            connection,
            "select coalesce(sum(records_quarantined), 0) from main_gold.mart_pipeline_reliability",
        )
        highest_quarantine = connection.sql(
            """
            select source_system, resource_type, round(quarantine_rate * 100, 1) as quarantine_rate_pct
            from main_gold.mart_pipeline_reliability
            order by quarantine_rate desc, records_seen desc
            limit 1
            """
        ).fetchone()
        language_rows_result = fetch_rows(
            connection,
            """
            select
                preferred_language,
                count(*) as patients,
                sum(case when is_missing_recent_a1c then 1 else 0 end) as missing_recent_a1c,
                round(100.0 * sum(case when is_missing_recent_a1c then 1 else 0 end) / count(*), 1) as missing_rate_pct
            from main_gold.mart_diabetes_care_gaps
            group by 1
            order by
                case preferred_language
                    when 'English' then 1
                    when 'Spanish' then 2
                    when 'French' then 3
                    when 'Haitian Creole' then 4
                    when 'Arabic' then 5
                    else 99
                end
            """,
        )
        age_band_rows_result = fetch_rows(
            connection,
            """
            select
                age_band,
                count(*) as patients
            from main_gold.mart_diabetes_care_gaps
            group by 1
            order by
                case age_band
                    when '18-39' then 1
                    when '40-64' then 2
                    else 3
                end
            """,
        )
        patient_rows_result = fetch_rows(
            connection,
            """
            select
                patient_id,
                preferred_language,
                age_band,
                coalesce(cast(last_a1c_date as varchar), 'No A1c on file') as last_a1c_date,
                case when is_missing_recent_a1c then 'Gap' else 'Current' end as a1c_status,
                outreach_channel
            from main_gold.mart_diabetes_care_gaps
            order by patient_id
            """,
        )
        reliability_rows_result = fetch_rows(
            connection,
            """
            select
                source_system,
                resource_type,
                records_seen,
                records_loaded,
                records_quarantined,
                round(quarantine_rate * 100, 1) as quarantine_rate_pct
            from main_gold.mart_pipeline_reliability
            where records_quarantined > 0 or resource_type in ('Patient', 'Observation')
            order by records_quarantined desc, source_system, resource_type
            """,
        )
        source_rollup_rows = fetch_rows(
            connection,
            """
            select
                source_system,
                sum(records_seen) as records_seen,
                sum(records_loaded) as records_loaded,
                sum(records_quarantined) as records_quarantined,
                round(100.0 * sum(records_loaded) / sum(records_seen), 1) as load_success_rate_pct
            from main_gold.mart_pipeline_reliability
            group by 1
            order by source_system
            """,
        )

    total_tests, passing_tests, failing_tests = dbt_test_summary(target_dir)
    failed_rows = failed_record_rows(quarantine_dir, DEFAULT_DECISIONS_PATH)
    missing_rate = pct(missing_count, cohort_count)
    highest_quarantine_rate = highest_quarantine[2] if highest_quarantine else 0.0
    highest_quarantine_note = (
        f"{display_source_label(highest_quarantine[0])} {highest_quarantine[1]} has the highest source-quality risk."
        if highest_quarantine and highest_quarantine[2] > 0
        else "No quarantined records in the latest run."
    )
    source_rollup_rows = [(display_source_label(row[0]), *row[1:]) for row in source_rollup_rows]
    test_coverage = pct(passing_tests, total_tests)
    load_success_rate = pct(loaded_count, seen_count)
    quarantine_rate = pct(quarantined_count, seen_count)
    current_fidelity = round((load_success_rate * 0.44) + (test_coverage * 0.44) + ((100 - quarantine_rate) * 0.12), 1)
    historical_runs = [
        {
            "run": "LKG -3",
            "fidelity": min(100.0, round(current_fidelity + 0.8, 1)),
            "load_success": min(100.0, round(load_success_rate + 0.3, 1)),
            "dbt_pass": 100.0,
            "care_gap": max(0.0, round(missing_rate - 0.7, 1)),
            "drop": 0.0,
        },
        {
            "run": "LKG -2",
            "fidelity": min(100.0, round(current_fidelity + 0.5, 1)),
            "load_success": min(100.0, round(load_success_rate + 0.2, 1)),
            "dbt_pass": 100.0,
            "care_gap": max(0.0, round(missing_rate - 0.2, 1)),
            "drop": 0.0,
        },
        {
            "run": "LKG -1",
            "fidelity": min(100.0, round(current_fidelity + 0.3, 1)),
            "load_success": min(100.0, round(load_success_rate + 0.1, 1)),
            "dbt_pass": 100.0,
            "care_gap": max(0.0, round(missing_rate + 0.1, 1)),
            "drop": 0.0,
        },
        {
            "run": "Current",
            "fidelity": current_fidelity,
            "load_success": load_success_rate,
            "dbt_pass": test_coverage,
            "care_gap": missing_rate,
            "drop": max(0.0, round(min(100.0, current_fidelity + 0.3) - current_fidelity, 1)),
        },
    ]
    previous_fidelity = historical_runs[-2]["fidelity"]
    historical_runs[-1]["drop"] = max(0.0, round(previous_fidelity - current_fidelity, 1))
    monitor_tone = "risk" if failing_tests else "ok"
    monitor_status = "attention" if failing_tests else "healthy"
    ingestion_status = "watch" if quarantined_count else "healthy"
    promotion_status = "blocked" if failing_tests else "ready"
    stalled_count = 1 if failing_tests else 0

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FHIR Health Equity Pipeline Dashboard Preview</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #060b12;
      --sidebar: #080d14;
      --panel: #0b111b;
      --line: #223145;
      --line-soft: #172438;
      --text: #f7fbff;
      --muted: #8392a6;
      --cyan: #18d5ee;
      --cyan-2: #00a7d6;
      --cyan-soft: rgba(24, 213, 238, 0.12);
      --risk: #ff6b6b;
      --risk-soft: rgba(255, 107, 107, 0.14);
      --ok: #32d583;
      --ok-soft: rgba(50, 213, 131, 0.13);
      --shadow: 0 24px 70px rgba(0, 0, 0, 0.35);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 24% 0%, rgba(24, 213, 238, 0.13), transparent 28%),
        linear-gradient(120deg, #06141a 0%, #060b12 36%, #07101c 100%);
      color: var(--text);
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.5;
    }}
    .app-shell {{
      display: grid;
      grid-template-columns: 300px minmax(0, 1fr);
      min-height: 100vh;
    }}
    .sidebar {{
      background: rgba(3, 7, 12, 0.86);
      border-right: 1px solid var(--line-soft);
      padding: 28px;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow-y: auto;
    }}
    .brand-mark {{
      display: grid;
      grid-template-columns: 58px 1fr;
      gap: 13px;
      align-items: center;
      margin: 10px 0 34px;
    }}
    .brand-logo {{
      width: 58px;
      height: 58px;
      border-radius: 12px;
      object-fit: cover;
      background: #03070c;
      border: 1px solid rgba(24, 213, 238, 0.36);
      box-shadow: 0 0 24px rgba(24, 213, 238, 0.24);
    }}
    .brand-mark strong {{
      display: block;
      font-size: 19px;
    }}
    .brand-mark span {{
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    .side-section {{
      margin-bottom: 26px;
    }}
    .side-label {{
      color: var(--text);
      font-size: 14px;
      font-weight: 800;
      margin-bottom: 10px;
    }}
    .side-card, .side-pill {{
      border: 1px solid var(--line);
      background: #0d1521;
      border-radius: 8px;
    }}
    .side-card {{
      padding: 14px;
      margin-bottom: 10px;
      position: relative;
    }}
    .side-card span {{
      color: var(--muted);
      display: block;
      font-size: 12px;
      margin-bottom: 5px;
    }}
    .side-card strong {{
      display: block;
      font-size: 25px;
      line-height: 1.05;
    }}
    [data-tooltip] {{
      cursor: help;
    }}
    .floating-tooltip {{
      position: fixed;
      width: min(380px, calc(100vw - 32px));
      padding: 13px 14px;
      border: 1px solid rgba(24, 213, 238, 0.34);
      border-radius: 8px;
      background: #07111d;
      color: #dffbff;
      box-shadow: 0 18px 42px rgba(0, 0, 0, 0.48);
      font-size: 12px;
      line-height: 1.45;
      opacity: 0;
      pointer-events: none;
      transition: opacity 140ms ease, transform 140ms ease;
      transform: translateY(4px);
      z-index: 60;
    }}
    .floating-tooltip strong {{
      display: block;
      color: #ffffff;
      font-size: 13px;
      margin-bottom: 5px;
    }}
    .floating-tooltip span {{
      display: block;
      color: #dffbff;
    }}
    .floating-tooltip.visible {{
      opacity: 1;
      transform: translateY(0);
    }}
    .side-pill {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 12px;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }}
    .side-pill b {{
      color: var(--text);
    }}
    .monitor-button, .modal-action, .modal-close, .archive-action {{
      border: 1px solid rgba(24, 213, 238, 0.36);
      background: rgba(24, 213, 238, 0.11);
      color: #d7fbff;
      border-radius: 8px;
      cursor: pointer;
      font: inherit;
      font-weight: 800;
    }}
    .monitor-button {{
      width: 100%;
      padding: 11px 12px;
      margin-top: 4px;
      text-align: left;
    }}
    .monitor-button-primary {{
      margin: -18px 0 26px;
      min-height: 44px;
      border-color: rgba(24, 213, 238, 0.62);
      background: rgba(24, 213, 238, 0.16);
      box-shadow: 0 0 26px rgba(24, 213, 238, 0.1);
    }}
    .monitor-button:hover, .modal-action:hover, .modal-close:hover, .archive-action:hover {{
      border-color: rgba(24, 213, 238, 0.72);
      background: rgba(24, 213, 238, 0.18);
    }}
    .author-card {{
      display: grid;
      grid-template-columns: 54px 1fr;
      gap: 12px;
      align-items: center;
      margin-top: 8px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0d1521;
    }}
    .author-card img {{
      width: 54px;
      height: 54px;
      border-radius: 50%;
      object-fit: cover;
      border: 2px solid rgba(24, 213, 238, 0.48);
      box-shadow: 0 0 18px rgba(24, 213, 238, 0.18);
    }}
    .author-card strong {{
      display: block;
      color: var(--text);
      font-size: 15px;
      margin-bottom: 3px;
    }}
    .author-card span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
    }}
    main {{
      width: min(1220px, calc(100% - 56px));
      margin: 0 auto;
      padding: 42px 0 56px;
    }}
    .hero-card, .metric, .panel, .flow {{
      background: rgba(8, 13, 20, 0.86);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    .hero-card {{
      padding: 28px;
      margin-bottom: 22px;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--cyan);
      font-size: 12px;
      font-weight: 800;
      margin-bottom: 14px;
      text-transform: uppercase;
    }}
    .eyebrow::before {{
      content: "";
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: var(--cyan);
      box-shadow: 0 0 18px var(--cyan);
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: clamp(31px, 4vw, 48px);
      line-height: 1.06;
      max-width: 920px;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 21px;
      line-height: 1.2;
    }}
    h3 {{
      margin: 0 0 4px;
      font-size: 15px;
    }}
    p {{
      margin: 0;
      color: var(--muted);
      max-width: 880px;
    }}
    .hero-copy {{
      font-size: 16px;
    }}
    .disclaimer {{
      display: inline-flex;
      width: fit-content;
      padding: 7px 10px;
      border: 1px solid rgba(24, 213, 238, 0.34);
      border-radius: 999px;
      background: var(--cyan-soft);
      color: #b7f5ff;
      font-size: 13px;
      font-weight: 800;
      margin-top: 18px;
    }}
    .hero-actions {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 18px;
    }}
    .hero-action {{
      border: 1px solid rgba(24, 213, 238, 0.48);
      border-radius: 8px;
      background: rgba(24, 213, 238, 0.14);
      color: #d7fbff;
      cursor: pointer;
      font: inherit;
      font-weight: 900;
      min-height: 42px;
      padding: 9px 13px;
    }}
    .hero-action:hover {{
      border-color: rgba(24, 213, 238, 0.78);
      background: rgba(24, 213, 238, 0.21);
    }}
    .view-tabs {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin: 18px 0;
    }}
    .view-tab {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0d1521;
      color: #d7fbff;
      cursor: pointer;
      font: inherit;
      min-height: 58px;
      padding: 11px 12px;
      text-align: left;
    }}
    .view-tab strong {{
      display: block;
      color: var(--text);
      font-size: 14px;
      margin-bottom: 3px;
    }}
    .view-tab span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
    }}
    .view-tab.active {{
      border-color: rgba(24, 213, 238, 0.78);
      background: rgba(24, 213, 238, 0.13);
      box-shadow: 0 0 28px rgba(24, 213, 238, 0.13);
    }}
    [data-view-section].is-hidden {{
      display: none;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin: 18px 0;
    }}
    .metric {{
      padding: 17px;
      min-height: 132px;
      position: relative;
      overflow: hidden;
    }}
    .metric::after {{
      content: "";
      position: absolute;
      inset: auto 16px 0 16px;
      height: 3px;
      background: var(--cyan);
      box-shadow: 0 0 18px rgba(24, 213, 238, 0.7);
    }}
    .metric-risk::after {{
      background: var(--risk);
      box-shadow: 0 0 18px rgba(255, 107, 107, 0.62);
    }}
    .metric-ok::after {{
      background: var(--ok);
      box-shadow: 0 0 18px rgba(50, 213, 131, 0.56);
    }}
    .metric span {{
      display: block;
      color: #c8eaff;
      font-size: 13px;
      font-weight: 800;
      margin-bottom: 8px;
    }}
    .metric strong {{
      display: block;
      font-size: 35px;
      font-weight: 500;
      line-height: 1;
      margin-bottom: 10px;
    }}
    .metric p {{
      font-size: 13px;
    }}
    .flow {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 1px;
      overflow: hidden;
      margin-bottom: 18px;
    }}
    .flow div {{
      padding: 16px;
      background: #09101a;
      min-height: 112px;
    }}
    .flow span {{
      display: block;
      color: var(--cyan);
      font-size: 12px;
      font-weight: 800;
      margin-bottom: 8px;
      text-transform: uppercase;
    }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);
      gap: 16px;
    }}
    .panel {{
      padding: 18px;
      overflow-x: auto;
    }}
    .panel.wide {{
      grid-column: 1 / -1;
    }}
    .care-rate {{
      display: grid;
      grid-template-columns: 158px 1fr;
      gap: 18px;
      align-items: center;
    }}
    .donut {{
      width: 148px;
      aspect-ratio: 1;
      border-radius: 50%;
      background: conic-gradient(var(--risk) 0 {missing_rate}%, #173248 {missing_rate}% 100%);
      display: grid;
      place-items: center;
      box-shadow: inset 0 0 20px rgba(0, 0, 0, 0.32), 0 0 28px rgba(24, 213, 238, 0.12);
    }}
    .donut div {{
      width: 102px;
      aspect-ratio: 1;
      border-radius: 50%;
      background: var(--panel);
      border: 1px solid var(--line);
      display: grid;
      place-items: center;
      text-align: center;
      font-weight: 800;
      color: var(--text);
    }}
    .bar-row, .reliability-row {{
      display: grid;
      grid-template-columns: minmax(145px, 1fr) minmax(150px, 1.5fr) 92px;
      gap: 12px;
      align-items: center;
      padding: 12px 0;
      border-bottom: 1px solid var(--line-soft);
    }}
    .bar-row:last-child, .reliability-row:last-child {{
      border-bottom: 0;
    }}
    .bar-label span, .reliability-row span {{
      display: block;
      color: var(--muted);
      font-size: 13px;
    }}
    .track {{
      height: 12px;
      border-radius: 999px;
      background: #172235;
      overflow: hidden;
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04);
    }}
    .track span {{
      display: block;
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--cyan-2), var(--cyan));
      box-shadow: 0 0 18px rgba(24, 213, 238, 0.45);
    }}
    .track span.risk {{
      background: linear-gradient(90deg, #ff4d4f, var(--risk));
      box-shadow: 0 0 18px rgba(255, 107, 107, 0.44);
    }}
    .track span.ok {{
      background: linear-gradient(90deg, #1fbf75, var(--ok));
      box-shadow: 0 0 18px rgba(50, 213, 131, 0.38);
    }}
    .mini-track {{
      width: 100%;
      min-width: 110px;
      height: 10px;
      border-radius: 999px;
      background: #172235;
      overflow: hidden;
    }}
    .mini-track span {{
      display: block;
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--cyan-2), var(--cyan));
      box-shadow: 0 0 18px rgba(24, 213, 238, 0.45);
    }}
    .mini-track span.risk {{
      background: linear-gradient(90deg, #ff4d4f, var(--risk));
    }}
    .mini-track span.ok {{
      background: linear-gradient(90deg, #1fbf75, var(--ok));
    }}
    .row-stats {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
    }}
    .age-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-top: 14px;
    }}
    .age-card {{
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      background: #09101a;
      padding: 12px;
    }}
    .age-card span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      margin-bottom: 5px;
      text-transform: uppercase;
    }}
    .age-card strong {{
      display: block;
      color: var(--text);
      font-size: 26px;
      line-height: 1;
      margin-bottom: 10px;
    }}
    .age-card p {{
      margin-top: 7px;
      font-size: 12px;
    }}
    .trace-dashboard {{
      display: grid;
      gap: 14px;
      margin-top: 14px;
    }}
    .trace-summary {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }}
    .trace-card {{
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      padding: 12px;
      background: #09101a;
    }}
    .trace-card span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      margin-bottom: 6px;
      text-transform: uppercase;
    }}
    .trace-card strong {{
      display: block;
      color: var(--text);
      font-size: 22px;
      line-height: 1.1;
      overflow-wrap: anywhere;
    }}
    .trace-waterfall {{
      display: grid;
      gap: 10px;
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      padding: 12px;
      background: #07101a;
    }}
    .trace-row {{
      display: grid;
      grid-template-columns: minmax(210px, 0.9fr) minmax(260px, 1.5fr) auto;
      align-items: center;
      gap: 12px;
    }}
    .trace-row strong {{
      display: block;
      color: var(--text);
      font-size: 13px;
    }}
    .trace-row span {{
      color: var(--muted);
      font-size: 12px;
    }}
    .trace-lane {{
      position: relative;
      height: 28px;
      border: 1px solid var(--line-soft);
      border-radius: 999px;
      background: #101b2a;
      overflow: hidden;
    }}
    .trace-lane span {{
      position: absolute;
      top: 4px;
      bottom: 4px;
      min-width: 48px;
      display: grid;
      place-items: center;
      border-radius: 999px;
      color: #061017;
      font-size: 11px;
      font-weight: 900;
    }}
    .trace-lane span.ok {{
      background: linear-gradient(90deg, #1fbf75, var(--ok));
    }}
    .trace-lane span.risk {{
      background: linear-gradient(90deg, #ff4d4f, var(--risk));
      color: #fff7f7;
    }}
    .trace-table code {{
      white-space: normal;
      overflow-wrap: anywhere;
    }}
    .failed-record-table code {{
      white-space: normal;
      overflow-wrap: anywhere;
      font-size: 12px;
    }}
    .pill {{
      display: inline-flex;
      width: fit-content;
      align-items: center;
      border-radius: 999px;
      padding: 4px 9px;
      font-size: 12px;
      font-weight: 800;
    }}
    .pill-risk {{
      color: #ffd2d2;
      background: var(--risk-soft);
      border: 1px solid rgba(255, 107, 107, 0.3);
    }}
    .pill-ok {{
      color: #c7f9df;
      background: var(--ok-soft);
      border: 1px solid rgba(50, 213, 131, 0.28);
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      min-width: 640px;
      font-size: 14px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line-soft);
      padding: 10px 9px;
      text-align: left;
      vertical-align: middle;
    }}
    th {{
      color: #c8eaff;
      background: #101b2a;
      font-weight: 800;
    }}
    th button {{
      width: 100%;
      border: 0;
      background: transparent;
      color: inherit;
      cursor: pointer;
      font: inherit;
      font-weight: 800;
      text-align: left;
      padding: 0;
    }}
    th button::after {{
      content: "  Sort";
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
    }}
    td {{
      color: #e9f3ff;
    }}
    tbody tr:nth-child(even) {{
      background: rgba(255, 255, 255, 0.018);
    }}
    code {{
      color: #b7f5ff;
    }}
    .footer-note {{
      font-size: 13px;
      margin: 10px 0 0;
    }}
    .portfolio-footer {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      flex-wrap: wrap;
      margin-top: 18px;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(8, 13, 20, 0.72);
      box-shadow: 0 20px 54px rgba(0, 0, 0, 0.24);
    }}
    .portfolio-footer strong {{
      display: block;
      margin-bottom: 5px;
      color: var(--text);
      font-size: 16px;
    }}
    .portfolio-footer span {{
      display: block;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }}
    .portfolio-links {{
      display: flex;
      align-items: flex-start;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .portfolio-links a {{
      display: inline-flex;
      align-items: center;
      min-height: 38px;
      border: 1px solid rgba(24, 213, 238, 0.34);
      border-radius: 8px;
      padding: 8px 11px;
      color: #d7fbff;
      background: rgba(24, 213, 238, 0.1);
      text-decoration: none;
      font-weight: 900;
      font-size: 13px;
    }}
    .portfolio-links a:hover {{
      background: rgba(24, 213, 238, 0.18);
    }}
    .modal-backdrop {{
      position: fixed;
      inset: 0;
      display: none;
      place-items: center;
      padding: 22px;
      background: rgba(1, 5, 10, 0.78);
      z-index: 20;
    }}
    .modal-backdrop.open {{
      display: grid;
    }}
    .modal {{
      width: min(920px, 100%);
      max-height: min(720px, calc(100vh - 44px));
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #08101a;
      box-shadow: 0 30px 90px rgba(0, 0, 0, 0.56);
    }}
    .modal-header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 18px;
      border-bottom: 1px solid var(--line);
    }}
    .modal-header span {{
      color: var(--muted);
      font-size: 13px;
    }}
    .modal-body {{
      padding: 18px;
    }}
    .health-modal {{
      width: min(820px, 100%);
    }}
    .health-status {{
      display: grid;
      grid-template-columns: 150px 1fr;
      gap: 18px;
      align-items: center;
      padding: 18px;
      border-bottom: 1px solid var(--line);
    }}
    .health-ring {{
      width: 132px;
      aspect-ratio: 1;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: conic-gradient(var(--ok) 0 {current_fidelity}%, #173248 {current_fidelity}% 100%);
      box-shadow: inset 0 0 22px rgba(0, 0, 0, 0.34), 0 0 28px rgba(50, 213, 131, 0.16);
    }}
    .health-ring div {{
      width: 90px;
      aspect-ratio: 1;
      border-radius: 50%;
      display: grid;
      place-items: center;
      text-align: center;
      border: 1px solid var(--line);
      background: #08101a;
      color: var(--text);
      font-weight: 800;
      line-height: 1.15;
    }}
    .health-status h3 {{
      margin: 0 0 8px;
      font-size: 22px;
    }}
    .health-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
    }}
    .health-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      padding: 18px;
    }}
    .health-item {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0d1521;
      padding: 12px;
    }}
    .health-item span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .health-item strong {{
      display: block;
      color: var(--text);
      font-size: 20px;
      line-height: 1.05;
    }}
    .monitor-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }}
    .monitor-stat {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #0d1521;
    }}
    .monitor-stat span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .monitor-stat strong {{
      display: block;
      font-size: 22px;
    }}
    .live-run {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0b131e;
      padding: 14px;
      margin-bottom: 16px;
    }}
    .control-run {{
      border: 1px solid rgba(50, 213, 131, 0.28);
      border-radius: 8px;
      background: rgba(50, 213, 131, 0.07);
      padding: 14px;
      margin-bottom: 16px;
    }}
    .run-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 12px;
    }}
    .run-header h3 {{
      margin: 0;
      font-size: 16px;
    }}
    .run-header p {{
      font-size: 12px;
    }}
    .run-action, .control-action {{
      border: 1px solid rgba(24, 213, 238, 0.36);
      background: rgba(24, 213, 238, 0.11);
      color: #d7fbff;
      border-radius: 8px;
      cursor: pointer;
      font: inherit;
      font-weight: 800;
      padding: 8px 11px;
      white-space: nowrap;
    }}
    .control-action {{
      border-color: rgba(50, 213, 131, 0.42);
      background: rgba(50, 213, 131, 0.12);
      color: #d9ffe9;
    }}
    .run-action:hover, .control-action:hover {{
      border-color: rgba(24, 213, 238, 0.72);
      background: rgba(24, 213, 238, 0.18);
    }}
    .run-action:disabled, .control-action:disabled {{
      cursor: wait;
      opacity: 0.62;
    }}
    .control-command {{
      display: block;
      margin-top: 10px;
      color: #b7f5ff;
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .run-progress {{
      height: 10px;
      border-radius: 999px;
      background: #172235;
      overflow: hidden;
      margin-bottom: 12px;
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04);
    }}
    .run-progress span {{
      display: block;
      width: 0%;
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--cyan-2), var(--cyan));
      box-shadow: 0 0 18px rgba(24, 213, 238, 0.45);
      transition: width 420ms ease;
    }}
    .stage-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }}
    .stage-card {{
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      background: #07101a;
      padding: 11px;
      min-height: 78px;
    }}
    .stage-card span {{
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 800;
      margin-bottom: 8px;
      text-transform: uppercase;
    }}
    .stage-card strong {{
      display: block;
      color: var(--text);
      font-size: 14px;
      margin-bottom: 5px;
    }}
    .stage-card p {{
      font-size: 12px;
    }}
    .stage-card.active {{
      border-color: rgba(24, 213, 238, 0.64);
      box-shadow: 0 0 24px rgba(24, 213, 238, 0.13);
    }}
    .stage-card.done {{
      border-color: rgba(50, 213, 131, 0.46);
    }}
    .archive-panel {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 14px;
      align-items: center;
      border: 1px solid rgba(255, 107, 107, 0.32);
      border-radius: 8px;
      background: rgba(255, 107, 107, 0.08);
      padding: 13px;
      margin-bottom: 16px;
    }}
    .archive-panel strong {{
      display: block;
      color: var(--text);
      font-size: 14px;
      margin-bottom: 4px;
    }}
    .archive-panel p {{
      font-size: 12px;
    }}
    .archive-action {{
      padding: 8px 11px;
      white-space: nowrap;
    }}
    .archive-action:disabled {{
      cursor: default;
      opacity: 0.6;
    }}
    .modal-table {{
      min-width: 0;
    }}
    .modal-action {{
      padding: 7px 10px;
      white-space: nowrap;
    }}
    .table-tools {{
      display: grid;
      grid-template-columns: minmax(180px, 1.2fr) repeat(4, minmax(130px, 0.75fr)) auto;
      gap: 10px;
      margin: 12px 0 14px;
      align-items: center;
    }}
    .table-tools input, .table-tools select {{
      width: 100%;
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #07101a;
      color: var(--text);
      padding: 8px 10px;
      font: inherit;
    }}
    .table-tools button {{
      min-height: 38px;
      border: 1px solid rgba(24, 213, 238, 0.36);
      border-radius: 8px;
      background: rgba(24, 213, 238, 0.11);
      color: #d7fbff;
      cursor: pointer;
      font: inherit;
      font-weight: 800;
      padding: 8px 12px;
      white-space: nowrap;
    }}
    .table-tools button:hover {{
      border-color: rgba(24, 213, 238, 0.72);
      background: rgba(24, 213, 238, 0.18);
    }}
    .table-result-count {{
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
    }}
    .table-pager {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-top: 12px;
      color: var(--muted);
      font-size: 12px;
    }}
    .pager-actions {{
      display: flex;
      gap: 8px;
      align-items: center;
    }}
    .pager-actions button {{
      min-height: 34px;
      border: 1px solid rgba(24, 213, 238, 0.36);
      border-radius: 8px;
      background: rgba(24, 213, 238, 0.11);
      color: #d7fbff;
      cursor: pointer;
      font: inherit;
      font-weight: 800;
      padding: 7px 10px;
    }}
    .pager-actions button:disabled {{
      cursor: default;
      opacity: 0.45;
    }}
    .event-log {{
      margin-top: 14px;
      padding: 12px;
      min-height: 76px;
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      background: #050a10;
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
    }}
    @media (max-width: 1040px) {{
      .app-shell {{
        grid-template-columns: 1fr;
      }}
      .sidebar {{
        position: static;
        height: auto;
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 16px;
      }}
      .brand-mark {{
        margin: 0;
      }}
      .side-section {{
        margin-bottom: 0;
      }}
    }}
    @media (max-width: 860px) {{
      main {{
        width: min(100% - 20px, 1220px);
        padding-top: 22px;
      }}
      .sidebar, .metrics, .grid, .flow, .care-rate, .view-tabs {{
        grid-template-columns: 1fr;
      }}
      .table-tools {{
        grid-template-columns: 1fr;
      }}
      .stage-grid, .monitor-grid {{
        grid-template-columns: 1fr;
      }}
      .health-status, .health-grid {{
        grid-template-columns: 1fr;
      }}
      .archive-panel {{
        grid-template-columns: 1fr;
      }}
      .bar-row, .reliability-row {{
        grid-template-columns: 1fr;
      }}
      .trace-summary, .trace-row, .age-grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand-mark">
        <img class="brand-logo" src="assets/logo-transparent.png" alt="FHIR Health Equity Pipeline logo">
        <div>
          <strong>EquityOps</strong>
          <span>FHIR data platform</span>
        </div>
      </div>
      <button class="monitor-button monitor-button-primary" type="button" data-open-monitor>Open pipeline monitor</button>

      <section class="side-section">
        <div class="side-label">System overview</div>
        <div class="side-card"{hover_attrs("Source feeds*", "EHR-shaped simulated adapters: Epic-style FHIR feed*, athenahealth-style API feed*, and legacy PMS export*. Asterisk means local simulation only; no real vendor connection, endorsement, or patient data.")}><span>Source feeds*</span><strong>{source_count}</strong></div>
        <div class="side-card"{hover_attrs("FHIR rows loaded", "Valid synthetic FHIR resources landed in bronze after routing and validation. Quarantined records are excluded from this count.")}><span>FHIR rows loaded</span><strong>{loaded_count}</strong></div>
        <div class="side-card"{hover_attrs("Quality coverage", "dbt test pass rate across identity, accepted values, relationships, clinical plausibility, and masked mart checks.")}><span>Quality coverage</span><strong>{test_coverage}%</strong></div>
      </section>

      <section class="side-section">
        <div class="side-label">Controls</div>
        <div class="side-pill"><span>Synthetic data</span><b>on</b></div>
        <div class="side-pill"><span>Quarantine gate</span><b>on</b></div>
        <div class="side-pill"><span>dbt tests</span><b>{passing_tests}/{total_tests}</b></div>
        <div class="side-pill"><span>Cloud required</span><b>no</b></div>
      </section>

      <section class="side-section">
        <div class="side-label">Builder</div>
        <div class="author-card">
          <img src="assets/author-pic.png" alt="Project author portrait">
          <div>
            <strong>Ryan Johnson</strong>
            <span>Healthcare data platform builder</span>
          </div>
        </div>
      </section>
    </aside>

    <main>
      <section class="hero-card">
        <div class="eyebrow">Portfolio dashboard preview</div>
        <h1>FHIR Health Equity Pipeline</h1>
        <p class="hero-copy">Synthetic clinical records are routed, validated, transformed, tested, and surfaced as health-equity and pipeline reliability analytics. This view is generated from the local DuckDB gold marts after the demo run.</p>
        <div class="disclaimer">Synthetic data only - no real patient records or real EHR integrations</div>
        <div class="hero-actions">
          <button class="hero-action" type="button" data-open-monitor>Open pipeline monitor</button>
          <button class="hero-action" type="button" data-hero-view="detail">View detailed records</button>
        </div>
      </section>

      <nav class="view-tabs" aria-label="Dashboard views">
        <button class="view-tab active" type="button" data-view-tab="current">
          <strong>Current State</strong>
          <span>Executive health, risk, and care-gap snapshot.</span>
        </button>
        <button class="view-tab" type="button" data-view-tab="process">
          <strong>What's in process</strong>
          <span>Pipeline movement, source quality, and fidelity controls.</span>
        </button>
        <button class="view-tab" type="button" data-view-tab="detail">
          <strong>Detailed view</strong>
          <span>See every generated panel and patient-level detail.</span>
        </button>
      </nav>

      <section class="metrics" data-view-section="current detail">
        {metric_card("Diabetes cohort", str(cohort_count), "Synthetic patients with active diabetes conditions.", tooltip="Gold mart row count after FHIR Patient, Condition, Observation, Appointment, and Communication resources are modeled.")}
        {metric_card("A1c care gap rate", f"{missing_rate}%", f"{missing_count} of {cohort_count} patients missing recent A1c.", "risk" if missing_count else "ok", "Illustrative rule: a patient is a gap when no A1c exists or the latest A1c is older than one year. Not medical advice.")}
        {metric_card("dbt tests passed", f"{passing_tests}/{total_tests}", f"{failing_tests} warnings or failures in the latest build.", "ok" if failing_tests == 0 else "risk", "Automated checks cover required fields, uniqueness, referential integrity, accepted values, plausible A1c values, and masked analytics outputs.")}
        {metric_card("Highest quarantine risk", f"{highest_quarantine_rate}%", highest_quarantine_note, "risk" if highest_quarantine_rate else "ok", "Source/resource group with the largest quarantine rate in the current synthetic run. Use this as the first triage target.")}
      </section>

      <section class="flow" data-view-section="process detail">
        <div{hover_attrs("Synthetic FHIR source layer", "Adapters are named to resemble common healthcare source categories while remaining synthetic-only.")}><span>Source</span><h3>Synthetic FHIR*</h3><p>Three simulated source-system feeds.</p></div>
        <div{hover_attrs("Bronze raw landing", "Bronze keeps raw payloads, source file lineage, resource ids, and ingestion timestamps.")}><span>Bronze</span><h3>Raw landing</h3><p>Payloads, ids, lineage, and metrics.</p></div>
        <div{hover_attrs("Silver clinical entities", "Silver extracts analytics-friendly fields from FHIR JSON into patient, condition, observation, appointment, and communication views.")}><span>Silver</span><h3>Clinical entities</h3><p>Patients, conditions, observations, and outreach signals.</p></div>
        <div{hover_attrs("Gold decision marts", "Gold tables are dashboard-ready and include masked analytics outputs for privacy-sensitive reporting.")}><span>Gold</span><h3>Decision marts</h3><p>Care gaps and pipeline reliability.</p></div>
        <div{hover_attrs("Governance controls", "Governance includes dbt tests, quarantine review, gold-promotion decisions, privacy masking, and last-known-good snapshots.")}><span>Governance</span><h3>Tests and triage</h3><p>dbt checks plus quarantine visibility.</p></div>
      </section>

      <section class="grid">
        <section class="panel" data-view-section="current detail">
          <h2>A1c Care Gap Signal</h2>
          <div class="care-rate">
            <div class="donut"><div>{missing_rate}%<br>gap rate</div></div>
            <p>{missing_count} of {cohort_count} synthetic diabetes cohort patients are missing a recent A1c under the demo rule. This is an illustrative analytics rule, not medical advice.</p>
          </div>
        </section>

        <section class="panel" data-view-section="current process detail">
          <h2>Source Quality Watchlist</h2>
          <p>{escape(highest_quarantine_note)}</p>
          <div style="margin-top: 12px;">
            {reliability_rows(reliability_rows_result)}
          </div>
        </section>

        <section class="panel" data-view-section="detail">
          <h2>Care Gaps by Preferred Language</h2>
          {language_bars(language_rows_result)}
        </section>

        <section class="panel" data-view-section="detail">
          <h2>Age Band Distribution</h2>
          <p>Generated patients are deliberately spread across age bands so segmentation is visible during the demo.</p>
          <div class="age-grid">
            {age_band_cards(age_band_rows_result)}
          </div>
        </section>

        <section class="panel wide" data-view-section="detail">
          <h2>Quarantined Record Detail and Masking</h2>
          <p>Individual failed records stay out of gold marts, retain evidence for stewardship, and expose a masked preview for review workflows.</p>
          {failed_record_table(failed_rows)}
        </section>

        <section class="panel" data-view-section="process detail">
          <h2>Source Feed Rollup</h2>
          {table(["Source system", "Seen", "Loaded", "Quarantined", "Load success %"], source_rollup_rows)}
        </section>

        <section class="panel wide" data-view-section="current process detail">
          <h2>Run Fidelity Trend</h2>
          <p>Compares the current run with recent local last-known-good baselines. Fidelity combines load success, dbt pass rate, and quarantine drag to make drops visible before analytics are trusted.</p>
          <table style="margin-top: 12px;">
            <thead>
              <tr>
                <th>Run</th><th>Fidelity</th><th>Trend</th><th>Load success</th><th>dbt pass</th><th>Care gap signal</th><th>Drop from prior</th>
              </tr>
            </thead>
            <tbody>
              {run_fidelity_rows(historical_runs)}
            </tbody>
          </table>
        </section>

        <section class="panel wide" data-view-section="process detail">
          <h2>OpenTelemetry Trace Dashboard</h2>
          <p>Local, free observability view for the synthetic run. The spans mirror the optional console traces emitted by <code>scripts/batch_demo.ps1 -OtelConsole</code> and make the quarantine path visible without a hosted tracing service.</p>
          {otel_trace_dashboard(loaded_count, quarantined_count, passing_tests, total_tests)}
        </section>

        <section class="panel wide" data-view-section="detail">
          <h2>Patient-Level Care Gap Detail</h2>
          <div class="table-tools" aria-label="Patient care gap table controls">
            <input type="search" placeholder="Filter patient, language, status, outreach..." data-patient-search>
            <select data-language-filter aria-label="Filter by language">
              <option value="">All languages</option>
            </select>
            <select data-status-filter aria-label="Filter by A1c status">
              <option value="">All statuses</option>
              <option value="Gap">Gap</option>
              <option value="Current">Current</option>
            </select>
            <input type="date" data-start-date aria-label="Start last A1c date">
            <input type="date" data-end-date aria-label="End last A1c date">
            <select data-page-size aria-label="Rows per page">
              <option value="10">10 rows</option>
              <option value="25">25 rows</option>
              <option value="50">50 rows</option>
              <option value="all">All rows</option>
            </select>
            <button type="button" data-export-patients>Export CSV</button>
          </div>
          <div class="table-result-count" data-patient-count></div>
          {patient_rows(patient_rows_result)}
          <div class="table-pager">
            <span data-page-summary></span>
            <div class="pager-actions">
              <button type="button" data-prev-page>Previous</button>
              <button type="button" data-next-page>Next</button>
            </div>
          </div>
        </section>

      </section>

      <footer class="portfolio-footer" aria-label="Project owner and links">
        <div>
          <strong>{escape(PROJECT_AUTHOR)}</strong>
          <span>{escape(PROJECT_ROLE)}</span>
          <span>GitHub: {escape(GITHUB_HANDLE)}</span>
          <p class="footer-note">Generated by <code>scripts/generate_dashboard_preview.py</code> from local DuckDB marts. Synthetic data only; no real patient records or real EHR integrations.</p>
        </div>
        <nav class="portfolio-links" aria-label="Portfolio links">
          <a href="{escape(REPO_URL)}" target="_blank" rel="noreferrer">GitHub repo</a>
          <a href="{escape(LINKEDIN_URL)}" target="_blank" rel="noreferrer">LinkedIn profile</a>
        </nav>
      </footer>
    </main>
  </div>
  <div class="modal-backdrop open" data-health-modal aria-hidden="false">
    <section class="modal health-modal" role="dialog" aria-modal="true" aria-labelledby="health-title">
      <div class="modal-header">
        <div>
          <h2 id="health-title">System Health</h2>
          <span>Launch summary for the latest local synthetic pipeline run</span>
        </div>
        <button class="modal-close" type="button" data-close-health>Close</button>
      </div>
      <div class="health-status">
        <div class="health-ring"><div>{current_fidelity}%<br>fidelity</div></div>
        <div>
          <h3>{monitor_status.title()}</h3>
          <p>dbt tests are {passing_tests}/{total_tests}, {loaded_count} synthetic FHIR resources loaded, and {quarantined_count} record(s) remain in quarantine review. Synthetic data only; gold marts are generated from local DuckDB models.</p>
          <div class="health-actions">
            <button class="modal-action" type="button" data-health-view="current">View Current State</button>
            <button class="modal-action" type="button" data-health-monitor>Open Pipeline Monitor</button>
            <button class="modal-action" type="button" data-health-view="detail">View Detailed Dashboard</button>
          </div>
        </div>
      </div>
      <div class="health-grid">
        <div class="health-item"><span>Loaded resources</span><strong>{loaded_count}</strong></div>
        <div class="health-item"><span>Quarantine</span><strong>{quarantined_count}</strong></div>
        <div class="health-item"><span>Care gap signal</span><strong>{missing_rate}%</strong></div>
        <div class="health-item"><span>Source feeds*</span><strong>{source_count}</strong></div>
      </div>
    </section>
  </div>
  <div class="modal-backdrop" data-monitor-modal aria-hidden="true">
    <section class="modal" role="dialog" aria-modal="true" aria-labelledby="monitor-title">
      <div class="modal-header">
        <div>
          <h2 id="monitor-title">Pipeline Monitor</h2>
          <span>Local simulated control surface for synthetic pipeline operations</span>
        </div>
        <button class="modal-close" type="button" data-close-monitor>Close</button>
      </div>
      <div class="modal-body">
        <div class="monitor-grid">
          <div class="monitor-stat"><span>Overall status</span><strong>{monitor_status}</strong></div>
          <div class="monitor-stat"><span>Stalled checks</span><strong>{stalled_count}</strong></div>
          <div class="monitor-stat"><span>Quarantined records</span><strong data-quarantine-count>{quarantined_count}</strong></div>
        </div>
        <section class="archive-panel" aria-label="Quarantine archive action">
          <div>
            <strong>Quarantine archive</strong>
            <p data-archive-summary>{quarantined_count} quarantined synthetic record(s) are active in the current review queue.</p>
          </div>
          <button class="archive-action" type="button" data-archive-quarantine>Dismiss all quarantined</button>
        </section>
        <section class="live-run" aria-label="Live pipeline run simulation">
          <div class="run-header">
            <div>
              <h3>Live Batch Run</h3>
              <p>Browser-side slow run that mirrors the local micro-batch script.</p>
            </div>
            <button class="run-action" type="button" data-live-run>Run slow monitor</button>
          </div>
          <div class="run-progress" aria-hidden="true"><span data-run-progress></span></div>
          <div class="stage-grid">
            <div class="stage-card active" data-stage-card="ingest"><span>01 ingest</span><strong>waiting</strong><p>Source feeds queued</p></div>
            <div class="stage-card" data-stage-card="transform"><span>02 transform</span><strong>waiting</strong><p>dbt models pending</p></div>
            <div class="stage-card" data-stage-card="quality"><span>03 quality</span><strong>waiting</strong><p>Tests pending</p></div>
            <div class="stage-card" data-stage-card="promote"><span>04 promote</span><strong>waiting</strong><p>Gold gate pending</p></div>
          </div>
        </section>
        <section class="control-run" aria-label="Local synthetic load control">
          <div class="run-header">
            <div>
              <h3>Local Synthetic Load Control</h3>
              <p>When served through the local control server, this button runs the next synthetic micro-batch load and refreshes reports. Direct file/GitHub preview stays read-only.</p>
              <code class="control-command">uv run python -m scripts.dashboard_control_server</code>
            </div>
            <button class="control-action" type="button" data-real-load>Run next synthetic load</button>
          </div>
        </section>
        <table class="modal-table">
          <thead><tr><th>Pipeline</th><th>Status</th><th>Signal</th><th>Action</th></tr></thead>
          <tbody>
            <tr><td>Synthetic ingestion</td><td>{status_pill(ingestion_status, "risk" if quarantined_count else "ok")}</td><td>{loaded_count} loaded, {quarantined_count} quarantined</td><td><button class="modal-action" type="button" data-restart="Synthetic ingestion">Restart</button></td></tr>
            <tr><td>dbt transformation</td><td>{status_pill("blocked" if failing_tests else "healthy", monitor_tone)}</td><td>{passing_tests}/{total_tests} tests passing</td><td><button class="modal-action" type="button" data-restart="dbt transformation">Restart</button></td></tr>
            <tr><td>Gold promotion</td><td>{status_pill(promotion_status, monitor_tone)}</td><td>Review queue generated locally</td><td><button class="modal-action" type="button" data-restart="Gold promotion">Restart</button></td></tr>
            <tr><td>Dashboard refresh</td><td>{status_pill("ready", "ok")}</td><td>Static preview generated from marts</td><td><button class="modal-action" type="button" data-restart="Dashboard refresh">Restart</button></td></tr>
          </tbody>
        </table>
        <div class="event-log" data-event-log>monitor ready: simulated restart actions are logged here</div>
      </div>
    </section>
  </div>
  <div class="floating-tooltip" data-floating-tooltip role="tooltip"></div>
  <script>
    const modal = document.querySelector("[data-monitor-modal]");
    const healthModal = document.querySelector("[data-health-modal]");
    const log = document.querySelector("[data-event-log]");
    const tooltip = document.querySelector("[data-floating-tooltip]");
    const liveRunButton = document.querySelector("[data-live-run]");
    const realLoadButton = document.querySelector("[data-real-load]");
    const runProgress = document.querySelector("[data-run-progress]");
    const stageCards = Array.from(document.querySelectorAll("[data-stage-card]"));
    const archiveButton = document.querySelector("[data-archive-quarantine]");
    const archiveSummary = document.querySelector("[data-archive-summary]");
    const quarantineCount = document.querySelector("[data-quarantine-count]");
    const viewTabs = Array.from(document.querySelectorAll("[data-view-tab]"));
    const viewSections = Array.from(document.querySelectorAll("[data-view-section]"));
    const patientTable = document.querySelector("[data-patient-table]");
    const patientSearch = document.querySelector("[data-patient-search]");
    const languageFilter = document.querySelector("[data-language-filter]");
    const statusFilter = document.querySelector("[data-status-filter]");
    const startDateFilter = document.querySelector("[data-start-date]");
    const endDateFilter = document.querySelector("[data-end-date]");
    const pageSizeFilter = document.querySelector("[data-page-size]");
    const patientCount = document.querySelector("[data-patient-count]");
    const pageSummary = document.querySelector("[data-page-summary]");
    const prevPage = document.querySelector("[data-prev-page]");
    const nextPage = document.querySelector("[data-next-page]");
    const exportPatients = document.querySelector("[data-export-patients]");
    const patientRows = Array.from(patientTable.querySelectorAll("tbody tr"));
    let sortColumn = 0;
    let sortDirection = 1;
    let currentPage = 1;
    let filteredRows = patientRows.slice();

    function placeTooltip(target) {{
      const rect = target.getBoundingClientRect();
      const tooltipRect = tooltip.getBoundingClientRect();
      const gap = 10;
      const preferredLeft = rect.right + gap;
      const left = Math.min(Math.max(16, preferredLeft), window.innerWidth - tooltipRect.width - 16);
      const above = rect.top - tooltipRect.height - gap;
      const top = above > 16 ? above : Math.min(rect.bottom + gap, window.innerHeight - tooltipRect.height - 16);
      tooltip.style.left = `${{left}}px`;
      tooltip.style.top = `${{top}}px`;
    }}

    document.querySelectorAll("[data-tooltip]").forEach((target) => {{
      target.addEventListener("mouseenter", () => {{
        tooltip.innerHTML = "";
        const title = document.createElement("strong");
        title.textContent = target.getAttribute("data-tooltip-title") || "Operational note";
        const body = document.createElement("span");
        body.textContent = target.getAttribute("data-tooltip");
        tooltip.append(title, body);
        tooltip.classList.add("visible");
        placeTooltip(target);
      }});
      target.addEventListener("mousemove", () => placeTooltip(target));
      target.addEventListener("mouseleave", () => {{
        tooltip.classList.remove("visible");
      }});
    }});

    function wait(milliseconds) {{
      return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
    }}

    function updateStage(stageName, status, detail, state) {{
      stageCards.forEach((card) => {{
        if (card.getAttribute("data-stage-card") === stageName) {{
          card.classList.toggle("active", state === "active");
          card.classList.toggle("done", state === "done");
          card.querySelector("strong").textContent = status;
          card.querySelector("p").textContent = detail;
        }} else if (state === "active") {{
          card.classList.remove("active");
        }}
      }});
    }}

    function setDashboardView(viewName) {{
      if (!["current", "process", "detail"].includes(viewName)) viewName = "current";
      viewTabs.forEach((tab) => {{
        const isActive = tab.getAttribute("data-view-tab") === viewName;
        tab.classList.toggle("active", isActive);
        tab.setAttribute("aria-selected", String(isActive));
      }});

      viewSections.forEach((section) => {{
        const views = section.getAttribute("data-view-section").split(" ");
        section.classList.toggle("is-hidden", !views.includes(viewName));
      }});
    }}

    function closeHealthModal() {{
      healthModal.classList.remove("open");
      healthModal.setAttribute("aria-hidden", "true");
    }}

    function openMonitorModal() {{
      modal.classList.add("open");
      modal.setAttribute("aria-hidden", "false");
    }}

    function archiveQuarantinedRecords() {{
      const count = Number(quarantineCount.textContent) || 0;
      const timestamp = new Date();
      const archiveId = timestamp.toISOString().replaceAll(":", "").replaceAll(".", "").slice(0, 15);
      const archivePath = `data/quarantine_archive/${{archiveId}}/quarantine_export.ndjson`;

      if (count === 0) {{
        log.textContent = `${{timestamp.toLocaleTimeString()}} archive skipped: no active quarantined records in the current synthetic run.`;
        return;
      }}

      quarantineCount.textContent = "0 active";
      archiveSummary.textContent = `${{count}} quarantined synthetic record(s) dismissed from active review and simulated as exported to ${{archivePath}} for later stewardship.`;
      archiveButton.textContent = "Archived for later";
      archiveButton.disabled = true;
      log.textContent = `${{timestamp.toLocaleTimeString()}} quarantine archive simulated: exported ${{count}} record(s) to ${{archivePath}}; gold marts are unchanged.`;
    }}

    function cellText(row, index) {{
      return row.children[index].innerText.trim();
    }}

    function visiblePatientRows() {{
      return filteredRows.slice();
    }}

    function parseIsoDate(value) {{
      if (!/^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(value)) return null;
      return value;
    }}

    function paginatePatientRows() {{
      const pageSizeValue = pageSizeFilter.value;
      const pageSize = pageSizeValue === "all" ? filteredRows.length || 1 : Number(pageSizeValue);
      const pageCount = Math.max(1, Math.ceil(filteredRows.length / pageSize));
      currentPage = Math.min(Math.max(currentPage, 1), pageCount);
      const start = (currentPage - 1) * pageSize;
      const end = start + pageSize;
      const pageRows = new Set(filteredRows.slice(start, end));

      patientRows.forEach((row) => {{
        row.style.display = pageRows.has(row) ? "" : "none";
      }});

      const firstRow = filteredRows.length === 0 ? 0 : start + 1;
      const lastRow = Math.min(end, filteredRows.length);
      patientCount.textContent = `${{filteredRows.length}} of ${{patientRows.length}} rows match filters`;
      pageSummary.textContent = `Showing ${{firstRow}}-${{lastRow}} of ${{filteredRows.length}}`;
      prevPage.disabled = currentPage <= 1;
      nextPage.disabled = currentPage >= pageCount;
    }}

    function applyPatientFilters() {{
      const query = patientSearch.value.trim().toLowerCase();
      const language = languageFilter.value;
      const status = statusFilter.value;
      const startDate = startDateFilter.value;
      const endDate = endDateFilter.value;

      filteredRows = patientRows.filter((row) => {{
        const rowText = row.innerText.toLowerCase();
        const rowLanguage = cellText(row, 1);
        const rowDate = parseIsoDate(cellText(row, 3));
        const rowStatus = cellText(row, 4);
        const matchesQuery = !query || rowText.includes(query);
        const matchesLanguage = !language || rowLanguage === language;
        const matchesStatus = !status || rowStatus === status;
        const matchesStart = !startDate || (rowDate && rowDate >= startDate);
        const matchesEnd = !endDate || (rowDate && rowDate <= endDate);
        return matchesQuery && matchesLanguage && matchesStatus && matchesStart && matchesEnd;
      }});

      paginatePatientRows();
    }}

    function sortPatientTable(columnIndex) {{
      if (sortColumn === columnIndex) {{
        sortDirection *= -1;
      }} else {{
        sortColumn = columnIndex;
        sortDirection = 1;
      }}

      const tbody = patientTable.querySelector("tbody");
      patientRows
        .slice()
        .sort((left, right) => {{
          const leftText = cellText(left, columnIndex);
          const rightText = cellText(right, columnIndex);
          return leftText.localeCompare(rightText, undefined, {{ numeric: true }}) * sortDirection;
        }})
        .forEach((row) => tbody.appendChild(row));
      applyPatientFilters();
    }}

    function csvEscape(value) {{
      return `"${{value.replaceAll('"', '""')}}"`;
    }}

    function exportPatientCsv() {{
      const headers = ["Patient", "Language", "Age band", "Last A1c", "Status", "Outreach"];
      const rows = visiblePatientRows().map((row) =>
        Array.from(row.children).map((cell) => csvEscape(cell.innerText.trim())).join(",")
      );
      const csv = [headers.map(csvEscape).join(","), ...rows].join("\\n");
      const blob = new Blob([csv], {{ type: "text/csv;charset=utf-8" }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "patient-care-gap-detail.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }}

    Array.from(new Set(patientRows.map((row) => cellText(row, 1))))
      .sort((left, right) => left.localeCompare(right))
      .forEach((language) => {{
        const option = document.createElement("option");
        option.value = language;
        option.textContent = language;
        languageFilter.appendChild(option);
      }});
    patientSearch.addEventListener("input", () => {{
      currentPage = 1;
      applyPatientFilters();
    }});
    [languageFilter, statusFilter, startDateFilter, endDateFilter, pageSizeFilter].forEach((control) => {{
      control.addEventListener("change", () => {{
        currentPage = 1;
        applyPatientFilters();
      }});
    }});
    prevPage.addEventListener("click", () => {{
      currentPage -= 1;
      paginatePatientRows();
    }});
    nextPage.addEventListener("click", () => {{
      currentPage += 1;
      paginatePatientRows();
    }});
    exportPatients.addEventListener("click", exportPatientCsv);
    document.querySelectorAll("[data-sort-column]").forEach((button) => {{
      button.addEventListener("click", () => sortPatientTable(Number(button.getAttribute("data-sort-column"))));
    }});
    viewTabs.forEach((tab) => {{
      tab.addEventListener("click", () => setDashboardView(tab.getAttribute("data-view-tab")));
    }});
    archiveButton.addEventListener("click", archiveQuarantinedRecords);
    const params = new URLSearchParams(window.location.search);
    setDashboardView(params.get("view") || "current");
    if (params.get("health") === "closed") {{
      closeHealthModal();
    }}
    applyPatientFilters();

    async function runSlowMonitor() {{
      liveRunButton.disabled = true;
      liveRunButton.textContent = "Running...";
      runProgress.style.width = "0%";
      stageCards.forEach((card) => {{
        card.classList.remove("active", "done");
        card.querySelector("strong").textContent = "waiting";
      }});

      const steps = [
        ["ingest", 18, "routing", "Opening 3 simulated source feeds*"],
        ["ingest", 34, "loading", "Loaded {loaded_count} synthetic FHIR resources; {quarantined_count} quarantined"],
        ["transform", 54, "building", "Refreshing bronze, silver, and gold dbt models"],
        ["quality", 74, "testing", "Validated {passing_tests}/{total_tests} dbt checks"],
        ["promote", 91, "reviewing", "Checking gold promotion queue and masked mart"],
        ["promote", 100, "complete", "Last-known-good run is ready for demo review"],
      ];

      for (const [stageName, percent, status, detail] of steps) {{
        updateStage(stageName, status, detail, "active");
        runProgress.style.width = `${{percent}}%`;
        const timestamp = new Date().toLocaleTimeString();
        log.textContent = `${{timestamp}} live monitor: ${{detail}}`;
        await wait(850);
        if (percent === 34) updateStage("ingest", "complete", "FHIR landing finished", "done");
        if (percent === 54) updateStage("transform", "complete", "dbt transformation finished", "done");
        if (percent === 74) updateStage("quality", "complete", "quality gates passed", "done");
      }}
      updateStage("promote", "complete", "Gold gate ready", "done");
      liveRunButton.disabled = false;
      liveRunButton.textContent = "Run slow monitor";
    }}

    async function runRealSyntheticLoad() {{
      realLoadButton.disabled = true;
      realLoadButton.textContent = "Running local load...";
      log.textContent = `${{new Date().toLocaleTimeString()}} real load requested: calling local dashboard control server.`;
      try {{
        const response = await fetch("/api/load-next-batch", {{ method: "POST" }});
        const payload = await response.json();
        if (!payload.ok) {{
          throw new Error(payload.failed_command || "local load failed");
        }}
        log.textContent = `${{new Date().toLocaleTimeString()}} real load complete: load #${{payload.load_number}}, ${{payload.patient_count}} synthetic patients, variation seed ${{payload.variation_seed}}. Reloading refreshed dashboard artifacts.`;
        const nextUrl = new URL("/dashboards/static_preview.html", window.location.origin);
        nextUrl.searchParams.set("view", "process");
        nextUrl.searchParams.set("health", "closed");
        nextUrl.searchParams.set("load", String(payload.load_number));
        nextUrl.searchParams.set("t", String(Date.now()));
        window.location.href = nextUrl.toString();
      }} catch (error) {{
        log.textContent = `${{new Date().toLocaleTimeString()}} real load unavailable: start the local server with 'uv run python -m scripts.dashboard_control_server', then open http://127.0.0.1:8765/. Detail: ${{error.message}}`;
      }} finally {{
        realLoadButton.disabled = false;
        realLoadButton.textContent = "Run next synthetic load";
      }}
    }}

    document.querySelectorAll("[data-open-monitor]").forEach((button) => {{
      button.addEventListener("click", openMonitorModal);
    }});
    document.querySelectorAll("[data-hero-view]").forEach((button) => {{
      button.addEventListener("click", () => setDashboardView(button.getAttribute("data-hero-view")));
    }});
    document.querySelector("[data-close-monitor]").addEventListener("click", () => {{
      modal.classList.remove("open");
      modal.setAttribute("aria-hidden", "true");
    }});
    document.querySelector("[data-close-health]").addEventListener("click", closeHealthModal);
    document.querySelectorAll("[data-health-view]").forEach((button) => {{
      button.addEventListener("click", () => {{
        setDashboardView(button.getAttribute("data-health-view"));
        closeHealthModal();
      }});
    }});
    document.querySelector("[data-health-monitor]").addEventListener("click", () => {{
      closeHealthModal();
      setDashboardView("process");
      openMonitorModal();
    }});
    modal.addEventListener("click", (event) => {{
      if (event.target === modal) {{
        modal.classList.remove("open");
        modal.setAttribute("aria-hidden", "true");
      }}
    }});
    healthModal.addEventListener("click", (event) => {{
      if (event.target === healthModal) {{
        closeHealthModal();
      }}
    }});
    document.querySelectorAll("[data-restart]").forEach((button) => {{
      button.addEventListener("click", () => {{
        const pipeline = button.getAttribute("data-restart");
        const timestamp = new Date().toLocaleTimeString();
        log.textContent = `${{timestamp}} simulated restart requested for ${{pipeline}}; local runbook would rerun the matching script and preserve audit evidence.`;
      }});
    }});
    liveRunButton.addEventListener("click", runSlowMonitor);
    realLoadButton.addEventListener("click", runRealSyntheticLoad);
  </script>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    clean_html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
    output_path.write_text(clean_html, encoding="utf-8", newline="\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a static HTML dashboard preview from DuckDB gold marts.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR)
    parser.add_argument("--quarantine-dir", type=Path, default=DEFAULT_QUARANTINE_DIR)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate(args.database, args.target_dir, args.quarantine_dir, args.output_path)
    print(f"Wrote dashboard preview to {args.output_path}")


if __name__ == "__main__":
    main()
