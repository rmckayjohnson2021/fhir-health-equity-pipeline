"""Serve the dashboard with a local-only control endpoint for synthetic loads."""

from __future__ import annotations

import argparse
import json
import subprocess
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "data" / "work" / "dashboard_control_state.json"
LOAD_STEPS = (60, 120, 180, 240)


def run_command(command: list[str], cwd: Path = ROOT) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "command": " ".join(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"load_index": 0}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def write_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def next_patient_count() -> tuple[int, int]:
    state = read_state()
    index = int(state.get("load_index", 0))
    patient_count = LOAD_STEPS[index % len(LOAD_STEPS)]
    state["load_index"] = index + 1
    state["last_patient_count"] = patient_count
    write_state(state)
    return patient_count, state["load_index"]


def run_synthetic_load(batch_size: int, delay_seconds: float) -> dict[str, Any]:
    patient_count, load_number = next_patient_count()
    commands = [
        [
            "uv",
            "run",
            "python",
            "-m",
            "scripts.run_batch_demo",
            "--patient-count",
            str(patient_count),
            "--batch-size",
            str(batch_size),
            "--delay-seconds",
            str(delay_seconds),
        ],
        ["uv", "run", "python", "-m", "scripts.ingest_unmapped_blobs", "--generate-sample", "--reset-table"],
        ["uv", "run", "dbt", "build", "--profiles-dir", "../dbt_profiles"],
        ["uv", "run", "python", "-m", "scripts.triage_quality_failures"],
        ["uv", "run", "python", "-m", "scripts.review_gold_promotion"],
        ["uv", "run", "python", "-m", "scripts.generate_dashboard_preview"],
        ["uv", "run", "python", "-m", "scripts.generate_fhir_mapping_workbench"],
        ["uv", "run", "python", "-m", "scripts.generate_privacy_report"],
        ["uv", "run", "python", "-m", "scripts.version_data_release"],
    ]
    results = []
    for command in commands:
        cwd = ROOT / "dbt_transforms" if command[:4] == ["uv", "run", "dbt", "build"] else ROOT
        result = run_command(command, cwd)
        results.append(result)
        if result["returncode"] != 0:
            return {
                "ok": False,
                "load_number": load_number,
                "patient_count": patient_count,
                "failed_command": result["command"],
                "results": results,
            }
    return {"ok": True, "load_number": load_number, "patient_count": patient_count, "results": results}


class DashboardControlHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, batch_size: int, delay_seconds: float, **kwargs: Any) -> None:
        self.batch_size = batch_size
        self.delay_seconds = delay_seconds
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self) -> None:
        if self.path in {"/", ""}:
            self.send_response(302)
            self.send_header("Location", "/dashboards/static_preview.html?view=process&health=closed")
            self.end_headers()
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path != "/api/load-next-batch":
            self.send_error(404, "Unknown control endpoint")
            return
        payload = run_synthetic_load(self.batch_size, self.delay_seconds)
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(200 if payload["ok"] else 500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the dashboard with a local-only synthetic load button.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address. Keep 127.0.0.1 for local-only demo use.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    def handler(*handler_args: Any, **handler_kwargs: Any) -> DashboardControlHandler:
        return DashboardControlHandler(
            *handler_args,
            batch_size=args.batch_size,
            delay_seconds=args.delay_seconds,
            **handler_kwargs,
        )

    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving dashboard controls at http://{args.host}:{args.port}/")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
