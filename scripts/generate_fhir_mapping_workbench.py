"""Generate an interactive local FHIR mapping workbench."""

from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
from typing import Any

import duckdb


DEFAULT_DATABASE = Path("data/warehouse/health_equity.duckdb")
DEFAULT_OUTPUT_PATH = Path("dashboards/fhir_mapping_workbench.html")
PROJECT_AUTHOR = "Ryan Johnson"
PROJECT_ROLE = "Healthcare data platform builder"
GITHUB_HANDLE = "rmckayjohnson2021"
REPO_URL = "https://github.com/rmckayjohnson2021/fhir-health-equity-pipeline"
LINKEDIN_URL = "https://www.linkedin.com/in/mckayjohnson/"
FORCED_CONVERSION_TARGET_TYPES = (
    "Observation",
    "QuestionnaireResponse",
    "ServiceRequest",
    "Communication",
    "DocumentReference",
    "Extension",
    "Basic",
)

FHIR_SCHEMA_SUBSET = {
    "R4": {
        "release": "4.0",
        "status": "Older baseline profile",
        "resources": {
            "Patient": ["id", "name", "gender", "birthDate", "address.postalCode", "communication.language"],
            "Observation": ["id", "status", "code", "subject", "effectiveDateTime", "valueQuantity"],
            "Communication": ["id", "status", "subject", "medium", "sent"],
        },
        "mappingSupport": {
            "food_access_text": {"status": "blocked", "target": "Extension", "reason": "No local R4 profile exists for this narrative SDOH field."},
            "housing_status_text": {"status": "blocked", "target": "Extension", "reason": "No local R4 profile exists for this narrative SDOH field."},
            "transportation_barrier": {"status": "candidate", "target": "Observation", "reason": "Can be represented only as a governed local Observation candidate."},
            "diabetes_followup_requested": {"status": "candidate", "target": "Communication", "reason": "Can inform outreach, but not structured as a gold care-gap signal in the local R4 profile."},
        },
    },
    "R4B": {
        "release": "4.3",
        "status": "Bridge profile",
        "resources": {
            "Patient": ["id", "name", "gender", "birthDate", "address.postalCode", "communication.language"],
            "Observation": ["id", "status", "category", "code", "subject", "effectiveDateTime", "valueQuantity", "note"],
            "QuestionnaireResponse": ["id", "status", "subject", "authored", "item.linkId", "item.answer"],
        },
        "mappingSupport": {
            "food_access_text": {"status": "candidate", "target": "QuestionnaireResponse.item.answer", "reason": "R4B bridge profile can retain the screening answer as structured questionnaire content."},
            "housing_status_text": {"status": "candidate", "target": "QuestionnaireResponse.item.answer", "reason": "R4B bridge profile can retain the screening answer as structured questionnaire content."},
            "transportation_barrier": {"status": "supported", "target": "Observation.category=social-history", "reason": "Local profile allows a social-history Observation candidate."},
            "diabetes_followup_requested": {"status": "candidate", "target": "ServiceRequest or Communication", "reason": "Needs a governed target choice before promotion."},
        },
    },
    "R5": {
        "release": "5.0",
        "status": "Expanded trial-use profile",
        "resources": {
            "Patient": ["id", "name", "gender", "birthDate", "address.postalCode", "communication.language"],
            "Observation": ["id", "status", "category", "code", "subject", "effectiveDateTime", "valueQuantity", "note", "triggeredBy"],
            "QuestionnaireResponse": ["id", "status", "subject", "authored", "item.linkId", "item.answer"],
            "ServiceRequest": ["id", "status", "intent", "subject", "reason", "occurrence"],
        },
        "mappingSupport": {
            "food_access_text": {"status": "supported", "target": "QuestionnaireResponse.item.answer", "reason": "Local R5 profile supports retaining narrative screening answers for downstream semantic mapping."},
            "housing_status_text": {"status": "supported", "target": "QuestionnaireResponse.item.answer", "reason": "Local R5 profile supports retaining narrative screening answers for downstream semantic mapping."},
            "transportation_barrier": {"status": "supported", "target": "Observation.category=social-history", "reason": "Local R5 profile supports this as a structured social-history signal."},
            "diabetes_followup_requested": {"status": "supported", "target": "ServiceRequest.reason", "reason": "Local R5 profile can promote this to a future follow-up signal after stewardship approval."},
        },
    },
}


SOURCE_BLOBS = [
    {
        "id": "screening-export-001",
        "source_system": "legacy_pms_simulated",
        "label": "SDOH screening export",
        "fields": {
            "housing_status_text": "temporarily staying with family",
            "food_access_text": "sometimes runs out before month end",
            "mapping_note": "Candidate for future Observation or QuestionnaireResponse mapping.",
        },
        "care_gap_delta": 1,
    },
    {
        "id": "referral-fax-001",
        "source_system": "athena_simulated",
        "label": "Referral summary text",
        "fields": {
            "transportation_barrier": "transportation barrier noted",
            "diabetes_followup_requested": "diabetes follow-up requested",
        },
        "care_gap_delta": 1,
    },
    {
        "id": "care-manager-note-001",
        "source_system": "epic_simulated",
        "label": "Care manager note",
        "fields": {
            "food_access_text": "patient reports food insecurity",
            "preferred_outreach_window": "prefers evening outreach",
        },
        "care_gap_delta": 0,
    },
]


def scalar(connection: duckdb.DuckDBPyConnection, query: str, default: Any = 0) -> Any:
    try:
        value = connection.sql(query).fetchone()[0]
    except duckdb.Error:
        return default
    return value if value is not None else default


def current_metrics(database: Path) -> dict[str, Any]:
    if not database.exists():
        return {"cohort": 0, "missing": 0, "rate": 0.0, "unmapped": len(SOURCE_BLOBS)}

    with duckdb.connect(str(database), read_only=True) as connection:
        cohort = scalar(connection, "select count(*) from main_gold.mart_diabetes_care_gaps", 0)
        missing = scalar(
            connection,
            "select count(*) from main_gold.mart_diabetes_care_gaps where is_missing_recent_a1c",
            0,
        )
        unmapped = scalar(connection, "select count(*) from bronze.unmapped_source_blobs", len(SOURCE_BLOBS))

    rate = round((missing / cohort) * 100, 1) if cohort else 0.0
    return {"cohort": cohort, "missing": missing, "rate": rate, "unmapped": unmapped}


def generate(database: Path, output_path: Path) -> None:
    metrics = current_metrics(database)
    schema_json = json.dumps(FHIR_SCHEMA_SUBSET, sort_keys=True)
    blobs_json = json.dumps(SOURCE_BLOBS, sort_keys=True)
    metrics_json = json.dumps(metrics, sort_keys=True)
    forced_target_json = json.dumps(FORCED_CONVERSION_TARGET_TYPES)

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FHIR Mapping Workbench</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #060b12;
      --panel: #0b111b;
      --panel-2: #0f1826;
      --line: #243348;
      --line-soft: #182438;
      --text: #f7fbff;
      --muted: #8da0b8;
      --cyan: #18d5ee;
      --ok: #32d583;
      --warn: #fdb022;
      --risk: #ff6b6b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 18% 0%, rgba(24, 213, 238, 0.14), transparent 28%),
        linear-gradient(120deg, #06141a 0%, var(--bg) 42%, #07101c 100%);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1280px, calc(100% - 40px));
      margin: 0 auto;
      padding: 36px 0 56px;
    }}
    header, .panel, .metric {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(8, 13, 20, 0.88);
      box-shadow: 0 24px 70px rgba(0, 0, 0, 0.33);
    }}
    header {{
      padding: 26px;
      margin-bottom: 18px;
    }}
    .eyebrow {{
      color: var(--cyan);
      font-size: 12px;
      font-weight: 900;
      text-transform: uppercase;
      margin-bottom: 10px;
    }}
    h1, h2, h3, p {{ margin-top: 0; }}
    h1 {{ margin-bottom: 10px; font-size: clamp(32px, 4vw, 50px); }}
    p {{ color: var(--muted); line-height: 1.5; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .metric {{ padding: 14px; }}
    .metric span {{ display: block; color: var(--muted); font-size: 12px; margin-bottom: 5px; }}
    .metric strong {{ display: block; font-size: 28px; }}
    .grid {{
      display: grid;
      grid-template-columns: 0.9fr 1.1fr;
      gap: 16px;
    }}
    .panel {{ padding: 18px; min-width: 0; }}
    .panel.wide {{ grid-column: 1 / -1; }}
    label {{ display: block; color: #cbefff; font-size: 13px; font-weight: 800; margin-bottom: 8px; }}
    select, input, textarea {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0d1521;
      color: var(--text);
      padding: 11px 12px;
      font: inherit;
    }}
    textarea {{ min-height: 84px; resize: vertical; }}
    .control-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px; }}
    .schema-list {{
      display: grid;
      gap: 10px;
    }}
    .schema-card {{
      padding: 12px;
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      background: #09101a;
    }}
    .schema-card strong {{ display: block; margin-bottom: 7px; }}
    .schema-card code {{ color: #b7f5ff; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ padding: 10px; border-bottom: 1px solid var(--line-soft); text-align: left; vertical-align: top; }}
    th {{ color: #cbefff; background: #101b2a; }}
    .pill {{
      display: inline-flex;
      border-radius: 999px;
      padding: 4px 9px;
      font-size: 12px;
      font-weight: 900;
    }}
    .pill-supported {{ color: #c7f9df; background: rgba(50, 213, 131, 0.14); border: 1px solid rgba(50, 213, 131, 0.28); }}
    .pill-candidate {{ color: #ffe6b0; background: rgba(253, 176, 34, 0.14); border: 1px solid rgba(253, 176, 34, 0.3); }}
    .pill-blocked {{ color: #ffd2d2; background: rgba(255, 107, 107, 0.14); border: 1px solid rgba(255, 107, 107, 0.3); }}
    button {{
      border: 1px solid rgba(24, 213, 238, 0.38);
      background: rgba(24, 213, 238, 0.12);
      color: #d7fbff;
      border-radius: 8px;
      padding: 10px 12px;
      font: inherit;
      font-weight: 900;
      cursor: pointer;
    }}
    button:hover {{ background: rgba(24, 213, 238, 0.2); }}
    .button-row {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }}
    .policy-note {{
      display: grid;
      grid-template-columns: 1.4fr 0.6fr;
      gap: 14px;
      align-items: center;
    }}
    .policy-status {{
      margin: 0;
      padding: 12px;
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      background: #09101a;
      color: #cfefff;
      font-size: 13px;
    }}
    .delta {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
    }}
    .delta div {{
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      padding: 12px;
      background: #09101a;
    }}
    .event-log {{
      min-height: 112px;
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      padding: 12px;
      background: #050a10;
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
      font-size: 12px;
      white-space: pre-wrap;
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
    .portfolio-footer span, .portfolio-footer p {{
      display: block;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
      margin: 0;
    }}
    .portfolio-footer p {{
      margin-top: 10px;
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
    .portfolio-links a:hover {{ background: rgba(24, 213, 238, 0.18); }}
    .source-json {{
      min-height: 150px;
      white-space: pre-wrap;
      color: #d6eaff;
      font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
      font-size: 13px;
    }}
    @media (max-width: 920px) {{
      .metrics, .grid, .control-row, .delta, .policy-note {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <div class="eyebrow">Interactive local workbench</div>
    <h1>FHIR Mapping Workbench</h1>
    <p>Query a local FHIR schema subset, compare R4/R4B/R5 mapping support, simulate a higher-version migration, and record forced conversion decisions. Synthetic data only. This is a portfolio control surface, not a full HL7 validator.</p>
  </header>

  <section class="metrics">
    <div class="metric"><span>Current cohort</span><strong data-metric="cohort"></strong></div>
    <div class="metric"><span>Current care gap signals</span><strong data-metric="missing"></strong></div>
    <div class="metric"><span>Current gap rate</span><strong data-metric="rate"></strong></div>
    <div class="metric"><span>Unmapped blobs</span><strong data-metric="unmapped"></strong></div>
  </section>

  <section class="panel wide" style="margin-bottom: 18px;">
    <h2>FHIR Version Policy</h2>
    <div class="policy-note">
      <p class="policy-status" data-policy-status>Static preview: version choices are browser-only unless the local dashboard control server is running.</p>
      <div class="button-row">
        <button type="button" data-revert-policy>Revert policy for future loads</button>
      </div>
    </div>
    <p>Simulation does not change data. A recorded migration applies from the selected timestamp forward; previous pipeline runs remain unchanged unless an explicit replay/backfill is run.</p>
  </section>

  <section class="grid">
    <section class="panel">
      <h2>Schema Query</h2>
      <div class="control-row">
        <div>
          <label for="version">FHIR version</label>
          <select id="version">
            <option value="R4">R4 / 4.0</option>
            <option value="R4B">R4B / 4.3</option>
            <option value="R5">R5 / 5.0</option>
          </select>
        </div>
        <div>
          <label for="schema-search">Search resources or fields</label>
          <input id="schema-search" value="Observation" placeholder="Observation, QuestionnaireResponse, food">
        </div>
      </div>
      <div class="schema-list" data-schema-results></div>
    </section>

    <section class="panel">
      <h2>Unmapped Source Blob</h2>
      <label for="blob">Source blob</label>
      <select id="blob"></select>
      <div class="schema-card source-json" data-blob-json></div>
    </section>

    <section class="panel wide">
      <h2>Mapping Candidates</h2>
      <table>
        <thead><tr><th>Source field</th><th>Status</th><th>Proposed target</th><th>Allowed forced FHIR type</th><th>Reason</th><th>Force</th></tr></thead>
        <tbody data-mapping-table></tbody>
      </table>
      <div class="control-row" style="margin-top: 14px;">
        <div>
          <label for="force-note">Forced conversion note</label>
          <textarea id="force-note" placeholder="Required when forcing a candidate or blocked mapping."></textarea>
        </div>
        <div>
          <label for="migration-time">Apply timestamp if migration is approved</label>
          <input id="migration-time" type="datetime-local">
          <div class="button-row">
            <button type="button" data-simulate>Simulate but do not apply</button>
            <button type="button" data-migrate>Record migration decision</button>
          </div>
        </div>
      </div>
      <div class="delta">
        <div><span>Baseline signals</span><strong data-delta="baseline"></strong></div>
        <div><span>Simulated signals</span><strong data-delta="simulated"></strong></div>
        <div><span>Projected delta</span><strong data-delta="delta"></strong></div>
      </div>
    </section>

    <section class="panel wide">
      <h2>Decision Log</h2>
      <div class="event-log" data-event-log>workbench ready</div>
    </section>
  </section>
  <footer class="portfolio-footer" aria-label="Project owner and links">
    <div>
      <strong>{escape(PROJECT_AUTHOR)}</strong>
      <span>{escape(PROJECT_ROLE)}</span>
      <span>GitHub: {escape(GITHUB_HANDLE)}</span>
      <p>Generated by <code>scripts/generate_fhir_mapping_workbench.py</code>. Synthetic data only; mapping decisions are local demo artifacts.</p>
    </div>
    <nav class="portfolio-links" aria-label="Portfolio links">
      <a href="{escape(REPO_URL)}" target="_blank" rel="noreferrer">GitHub repo</a>
      <a href="{escape(LINKEDIN_URL)}" target="_blank" rel="noreferrer">LinkedIn profile</a>
    </nav>
  </footer>
</main>

<script>
const schemas = {schema_json};
const blobs = {blobs_json};
const metrics = {metrics_json};
const forcedTargetTypes = {forced_target_json};
const versionSelect = document.querySelector("#version");
const schemaSearch = document.querySelector("#schema-search");
const schemaResults = document.querySelector("[data-schema-results]");
const blobSelect = document.querySelector("#blob");
const blobJson = document.querySelector("[data-blob-json]");
const mappingTable = document.querySelector("[data-mapping-table]");
const forceNote = document.querySelector("#force-note");
const migrationTime = document.querySelector("#migration-time");
const eventLog = document.querySelector("[data-event-log]");
const policyStatus = document.querySelector("[data-policy-status]");
const revertPolicyButton = document.querySelector("[data-revert-policy]");
let selectedForcedFields = new Map();

document.querySelector('[data-metric="cohort"]').textContent = metrics.cohort;
document.querySelector('[data-metric="missing"]').textContent = metrics.missing;
document.querySelector('[data-metric="rate"]').textContent = `${{metrics.rate}}%`;
document.querySelector('[data-metric="unmapped"]').textContent = metrics.unmapped;

function pillElement(status) {{
  const span = document.createElement("span");
  span.className = `pill pill-${{status}}`;
  span.textContent = status;
  return span;
}}

function activeBlob() {{
  return blobs.find((blob) => blob.id === blobSelect.value) || blobs[0];
}}

function activeSchema() {{
  return schemas[versionSelect.value];
}}

function renderSchema() {{
  const schema = activeSchema();
  const query = schemaSearch.value.toLowerCase();
  schemaResults.replaceChildren();
  const summary = document.createElement("p");
  summary.textContent = `${{versionSelect.value}} ${{schema.release}} - ${{schema.status}}`;
  schemaResults.appendChild(summary);
  Object.entries(schema.resources).forEach(([resource, fields]) => {{
    const matches = resource.toLowerCase().includes(query) || fields.some((field) => field.toLowerCase().includes(query));
    if (matches || !query) {{
      const card = document.createElement("div");
      const title = document.createElement("strong");
      const code = document.createElement("code");
      card.className = "schema-card";
      title.textContent = resource;
      code.textContent = fields.join(", ");
      card.append(title, code);
      schemaResults.appendChild(card);
    }}
  }});
}}

function renderBlobOptions() {{
  blobSelect.replaceChildren();
  blobs.forEach((blob) => {{
    const option = document.createElement("option");
    option.value = blob.id;
    option.textContent = `${{blob.label}} - ${{blob.source_system}}`;
    blobSelect.appendChild(option);
  }});
}}

function renderBlob() {{
  const blob = activeBlob();
  blobJson.textContent = JSON.stringify(blob.fields, null, 2);
}}

function renderMappings() {{
  const schema = activeSchema();
  const blob = activeBlob();
  selectedForcedFields.clear();
  mappingTable.replaceChildren();
  Object.entries(blob.fields).forEach(([field]) => {{
    const support = schema.mappingSupport[field] || {{
      status: "blocked",
      target: "No governed target",
      reason: "The local schema subset has no mapping for this field."
    }};
    const row = document.createElement("tr");
    const fieldCell = document.createElement("td");
    const fieldCode = document.createElement("code");
    const statusCell = document.createElement("td");
    const targetCell = document.createElement("td");
    const forcedTypeCell = document.createElement("td");
    const reasonCell = document.createElement("td");
    const forceCell = document.createElement("td");
    const targetSelect = document.createElement("select");
    const checkbox = document.createElement("input");

    fieldCode.textContent = field;
    fieldCell.appendChild(fieldCode);
    statusCell.appendChild(pillElement(support.status));
    targetCell.textContent = support.target;
    targetSelect.setAttribute("data-force-target", field);
    targetSelect.disabled = true;
    forcedTargetTypes.forEach((targetType) => {{
      const option = document.createElement("option");
      option.value = targetType;
      option.textContent = targetType;
      targetSelect.appendChild(option);
    }});
    forcedTypeCell.appendChild(targetSelect);
    reasonCell.textContent = support.reason;
    checkbox.type = "checkbox";
    checkbox.setAttribute("data-force-field", field);
    checkbox.setAttribute("aria-label", `Force ${{field}}`);
    forceCell.appendChild(checkbox);
    row.append(fieldCell, statusCell, targetCell, forcedTypeCell, reasonCell, forceCell);
    mappingTable.appendChild(row);
  }});
  document.querySelectorAll("[data-force-field]").forEach((checkbox) => {{
    const field = checkbox.getAttribute("data-force-field");
    const targetSelect = document.querySelector(`[data-force-target="${{field}}"]`);
    checkbox.addEventListener("change", () => {{
      targetSelect.disabled = !checkbox.checked;
      if (checkbox.checked) selectedForcedFields.set(field, targetSelect.value);
      else selectedForcedFields.delete(field);
      renderDelta(false);
    }});
  }});
  document.querySelectorAll("[data-force-target]").forEach((targetSelect) => {{
    targetSelect.addEventListener("change", () => {{
      const field = targetSelect.getAttribute("data-force-target");
      if (selectedForcedFields.has(field)) selectedForcedFields.set(field, targetSelect.value);
    }});
  }});
  renderDelta(false);
}}

function renderDelta(simulated) {{
  const blob = activeBlob();
  const supportValues = Object.keys(blob.fields).map((field) => activeSchema().mappingSupport[field]?.status || "blocked");
  const supportedCount = supportValues.filter((status) => status === "supported").length;
  const candidateCount = supportValues.filter((status) => status === "candidate").length;
  const forceBonus = selectedForcedFields.size > 0 ? 1 : 0;
  const versionBonus = simulated ? Math.min(blob.care_gap_delta, supportedCount > 0 ? 1 : 0) : 0;
  const candidateBonus = simulated && candidateCount > 0 && versionSelect.value !== "R4" ? 1 : 0;
  const projected = metrics.missing + Math.max(versionBonus, candidateBonus, forceBonus);
  document.querySelector('[data-delta="baseline"]').textContent = metrics.missing;
  document.querySelector('[data-delta="simulated"]').textContent = projected;
  document.querySelector('[data-delta="delta"]').textContent = `+${{Math.max(0, projected - metrics.missing)}}`;
}}

function log(message) {{
  const timestamp = new Date().toLocaleString();
  eventLog.textContent = `${{timestamp}} ${{message}}\\n` + eventLog.textContent;
}}

async function requestPolicy(payload) {{
  const response = await fetch("/api/fhir-version-policy", {{
    method: "POST",
    headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify(payload)
  }});
  const body = await response.json();
  if (!response.ok || !body.ok) throw new Error(body.error || "policy request failed");
  return body;
}}

async function loadPolicy() {{
  try {{
    const response = await fetch("/api/fhir-version-policy");
    if (!response.ok) throw new Error("policy endpoint unavailable");
    const body = await response.json();
    const policy = body.policy;
    policyStatus.textContent = `Local policy active: ${{policy.active_version}} / ${{policy.mode}} / effective ${{policy.effective_at || "not applied"}}. Previous runs remain unchanged; policy report: ${{body.report}}.`;
  }} catch (error) {{
    policyStatus.textContent = "Static preview: decisions are browser-only. Start `uv run python -m scripts.dashboard_control_server` and open http://127.0.0.1:8765/ to persist FHIR version policy decisions.";
  }}
}}

versionSelect.addEventListener("change", () => {{ renderSchema(); renderMappings(); renderBlob(); }});
schemaSearch.addEventListener("input", renderSchema);
blobSelect.addEventListener("change", () => {{ renderBlob(); renderMappings(); }});
document.querySelector("[data-simulate]").addEventListener("click", () => {{
  renderDelta(true);
  log(`simulated ${{versionSelect.value}} migration for ${{activeBlob().id}}; no data was changed`);
}});
document.querySelector("[data-migrate]").addEventListener("click", async () => {{
  if (!migrationTime.value) {{
    log("migration decision blocked: timestamp is required");
    return;
  }}
  if (selectedForcedFields.size > 0 && !forceNote.value.trim()) {{
    log("forced conversion blocked: note is required");
    return;
  }}
  const forced = Array.from(selectedForcedFields.entries()).map(([field, target]) => `${{field}}->${{target}}`);
  log(`recorded migration decision to ${{versionSelect.value}} effective ${{migrationTime.value}} for ${{activeBlob().id}}; forced_mappings=${{forced.join(",") || "none"}}; note=${{forceNote.value.trim() || "not forced"}}`);
  try {{
    const body = await requestPolicy({{
      action: "record",
      version: versionSelect.value,
      mode: "apply_forward",
      effective_at: migrationTime.value,
      note: forceNote.value.trim() || `Approved ${{versionSelect.value}} for future synthetic loads.`,
      forced_mappings: Array.from(selectedForcedFields.entries()).map(([field, targetType]) => ({{
        field,
        target_type: targetType
      }}))
    }});
    policyStatus.textContent = `Persisted local policy: ${{body.policy.active_version}} effective ${{body.policy.effective_at}}. Report: ${{body.report}}.`;
    log(`persisted FHIR version policy to ${{body.report}}; applies from timestamp forward`);
  }} catch (error) {{
    log(`policy persistence skipped: start dashboard_control_server to persist local decisions. Detail: ${{error.message}}`);
  }}
}});
revertPolicyButton.addEventListener("click", async () => {{
  try {{
    const body = await requestPolicy({{
      action: "revert",
      effective_at: new Date().toISOString(),
      note: "Reverted from mapping workbench for future synthetic loads."
    }});
    policyStatus.textContent = `Reverted local policy to ${{body.policy.active_version}} for future loads. Previous runs remain unchanged. Report: ${{body.report}}.`;
    log(`reverted FHIR version policy for future loads; report=${{body.report}}`);
  }} catch (error) {{
    log(`policy revert unavailable: start dashboard_control_server to use local persistence. Detail: ${{error.message}}`);
  }}
}});

renderBlobOptions();
renderSchema();
renderBlob();
renderMappings();
loadPolicy();
</script>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    clean_html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
    output_path.write_text(clean_html, encoding="utf-8", newline="\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an interactive FHIR mapping workbench HTML artifact.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generate(args.database, args.output_path)
    print(f"Wrote FHIR mapping workbench to {args.output_path}")


if __name__ == "__main__":
    main()
