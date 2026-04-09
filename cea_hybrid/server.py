"""HTTP server and background analysis job state for the browser UI."""

import json
import os
import threading
import time
from copy import deepcopy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from blowdown_hybrid import BlowdownCancelled, estimate_total_steps, run_blowdown
from blowdown_hybrid.ui_backend import (
    build_config_from_payload as build_blowdown_config_from_payload,
    build_error_response as build_blowdown_error_response,
    build_not_run_response,
    build_pending_response,
    build_preview_response as build_blowdown_preview_response,
    build_running_response,
    build_ui_response as build_blowdown_ui_response,
)
from cea_hybrid.sweep import SweepCancelled, count_total_combinations, run_sweep
from cea_hybrid.ui_backend import (
    build_default_ui_config,
    build_raw_config_from_payload,
    build_ui_response,
)


HOST = "127.0.0.1"
PORT = 8000
ROOT_DIR = Path(__file__).resolve().parent.parent
UI_DIR = ROOT_DIR / "ui"
JOB_LOCK = threading.Lock()
SWEEP_JOB = {
    "job_id": 0,
    "status": "idle",
    "job_type": None,
    "phase": None,
    "message": "Ready to run.",
    "progress_completed": 0,
    "progress_total": 0,
    "progress_ratio": 0.0,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "result": None,
    "thread": None,
    "cancel_event": None,
}


def build_job_snapshot(include_result=True):
    with JOB_LOCK:
        snapshot = {
            "job_id": SWEEP_JOB["job_id"],
            "status": SWEEP_JOB["status"],
            "job_type": SWEEP_JOB["job_type"],
            "phase": SWEEP_JOB["phase"],
            "message": SWEEP_JOB["message"],
            "progress_completed": SWEEP_JOB["progress_completed"],
            "progress_total": SWEEP_JOB["progress_total"],
            "progress_ratio": SWEEP_JOB["progress_ratio"],
            "started_at": SWEEP_JOB["started_at"],
            "finished_at": SWEEP_JOB["finished_at"],
            "error": SWEEP_JOB["error"],
        }
        if include_result and SWEEP_JOB["result"] is not None:
            snapshot["result"] = SWEEP_JOB["result"]
    return snapshot


def _set_progress(job_id, completed, total, phase, message):
    with JOB_LOCK:
        if SWEEP_JOB["job_id"] != job_id or SWEEP_JOB["status"] not in {"running", "stopping"}:
            return
        SWEEP_JOB["phase"] = phase
        SWEEP_JOB["progress_completed"] = int(completed)
        SWEEP_JOB["progress_total"] = int(total)
        SWEEP_JOB["progress_ratio"] = 0.0 if total <= 0 else max(0.0, min(1.0, completed / total))
        SWEEP_JOB["message"] = message


def _finish_job(job_id, status, message, result=None, error=None, progress_completed=None, progress_total=None):
    with JOB_LOCK:
        if SWEEP_JOB["job_id"] != job_id:
            return
        if progress_completed is not None:
            SWEEP_JOB["progress_completed"] = int(progress_completed)
        if progress_total is not None:
            SWEEP_JOB["progress_total"] = int(progress_total)
        total = SWEEP_JOB["progress_total"]
        completed = SWEEP_JOB["progress_completed"]
        SWEEP_JOB["progress_ratio"] = 0.0 if total <= 0 else max(0.0, min(1.0, completed / total))
        SWEEP_JOB["status"] = status
        SWEEP_JOB["job_type"] = None
        SWEEP_JOB["phase"] = None
        SWEEP_JOB["message"] = message
        SWEEP_JOB["finished_at"] = time.time()
        SWEEP_JOB["error"] = error
        SWEEP_JOB["result"] = result
        SWEEP_JOB["thread"] = None
        SWEEP_JOB["cancel_event"] = None


def run_sweep_job(job_id, cea_config, blowdown_config, cancel_event):
    sweep_total = count_total_combinations(cea_config)
    blowdown_total = estimate_total_steps(blowdown_config) if blowdown_config["auto_run_after_cea"] else 0
    total_progress = sweep_total + blowdown_total
    response = None
    seed_case = None

    try:
        sweep_started_at = time.perf_counter()
        sweep_results = run_sweep(
            cea_config,
            progress_callback=lambda completed, _: _set_progress(
                job_id,
                completed,
                total_progress,
                "cea",
                f"Running CEA sweep {completed}/{sweep_total}...",
            ),
            cancel_event=cancel_event,
        )
        sweep_runtime_seconds = time.perf_counter() - sweep_started_at
        response = build_ui_response(cea_config, sweep_results, sweep_runtime_seconds)
        seed_case = deepcopy(response["best_isp_case"]["case"])

        if not blowdown_config["auto_run_after_cea"]:
            response["blowdown"] = build_not_run_response(blowdown_config, seed_case)
            _finish_job(
                job_id,
                "completed",
                "CEA sweep complete.",
                result=response,
                progress_completed=sweep_total,
                progress_total=total_progress,
            )
            return

        response["blowdown"] = build_running_response(blowdown_config, seed_case)
        with JOB_LOCK:
            if SWEEP_JOB["job_id"] != job_id:
                return
            SWEEP_JOB["result"] = response
            SWEEP_JOB["phase"] = "blowdown"
            SWEEP_JOB["message"] = response["blowdown"]["message"]

        blowdown_started_at = time.perf_counter()
        blowdown_runtime = run_blowdown(
            blowdown_config,
            seed_case,
            progress_callback=lambda completed, total: _set_progress(
                job_id,
                sweep_total + completed,
                total_progress,
                "blowdown",
                f"Running preliminary 0D blowdown {completed}/{total}...",
            ),
            cancel_event=cancel_event,
        )
        blowdown_runtime_seconds = time.perf_counter() - blowdown_started_at
        response["blowdown"] = build_blowdown_ui_response(
            blowdown_config,
            seed_case,
            blowdown_runtime,
            blowdown_runtime_seconds,
        )
        _finish_job(
            job_id,
            "completed",
            "CEA sweep and preliminary 0D blowdown complete.",
            result=response,
            progress_completed=total_progress,
            progress_total=total_progress,
        )
    except (SweepCancelled, BlowdownCancelled):
        if response is not None and seed_case is not None:
            response["blowdown"] = build_pending_response(
                blowdown_config,
                seed_case,
                status="cancelled",
                message="Preliminary 0D blowdown run cancelled.",
            )
        _finish_job(job_id, "cancelled", "Analysis cancelled.", result=response)
    except Exception as exc:
        if response is not None and seed_case is not None:
            response["blowdown"] = build_blowdown_error_response(blowdown_config, seed_case, str(exc))
            _finish_job(
                job_id,
                "completed",
                "CEA sweep complete. Preliminary 0D blowdown failed.",
                result=response,
                progress_completed=sweep_total,
                progress_total=total_progress,
            )
            return
        _finish_job(job_id, "error", "CEA sweep failed.", error=str(exc))


def run_blowdown_job(job_id, blowdown_config, seed_case, base_result, cancel_event):
    total_progress = estimate_total_steps(blowdown_config)
    result = deepcopy(base_result)

    try:
        blowdown_started_at = time.perf_counter()
        blowdown_runtime = run_blowdown(
            blowdown_config,
            seed_case,
            progress_callback=lambda completed, total: _set_progress(
                job_id,
                completed,
                total_progress,
                "blowdown",
                f"Running preliminary 0D blowdown {completed}/{total}...",
            ),
            cancel_event=cancel_event,
        )
        blowdown_runtime_seconds = time.perf_counter() - blowdown_started_at
        result["blowdown"] = build_blowdown_ui_response(
            blowdown_config,
            seed_case,
            blowdown_runtime,
            blowdown_runtime_seconds,
        )
        _finish_job(
            job_id,
            "completed",
            "Preliminary 0D blowdown complete.",
            result=result,
            progress_completed=total_progress,
            progress_total=total_progress,
        )
    except BlowdownCancelled:
        result["blowdown"] = build_pending_response(
            blowdown_config,
            seed_case,
            status="cancelled",
            message="Preliminary 0D blowdown run cancelled.",
        )
        _finish_job(job_id, "cancelled", "Preliminary 0D blowdown cancelled.", result=result)
    except Exception as exc:
        result["blowdown"] = build_blowdown_error_response(blowdown_config, seed_case, str(exc))
        _finish_job(job_id, "error", "Preliminary 0D blowdown failed.", result=result, error=str(exc))


def start_sweep_job(payload):
    cea_config = build_raw_config_from_payload(payload)
    blowdown_config = build_blowdown_config_from_payload(payload.get("blowdown", {}))
    total_combinations = count_total_combinations(cea_config)
    total_progress = total_combinations + (
        estimate_total_steps(blowdown_config) if blowdown_config["auto_run_after_cea"] else 0
    )
    cancel_event = threading.Event()

    with JOB_LOCK:
        if SWEEP_JOB["status"] in {"running", "stopping"}:
            raise RuntimeError("An analysis is already running.")
        job_id = SWEEP_JOB["job_id"] + 1
        SWEEP_JOB["job_id"] = job_id
        SWEEP_JOB["status"] = "running"
        SWEEP_JOB["job_type"] = "sweep"
        SWEEP_JOB["phase"] = "cea"
        SWEEP_JOB["message"] = f"Running CEA sweep 0/{total_combinations}..."
        SWEEP_JOB["progress_completed"] = 0
        SWEEP_JOB["progress_total"] = total_progress
        SWEEP_JOB["progress_ratio"] = 0.0
        SWEEP_JOB["started_at"] = time.time()
        SWEEP_JOB["finished_at"] = None
        SWEEP_JOB["error"] = None
        SWEEP_JOB["result"] = None
        SWEEP_JOB["cancel_event"] = cancel_event
        worker = threading.Thread(
            target=run_sweep_job,
            args=(job_id, cea_config, blowdown_config, cancel_event),
            daemon=True,
        )
        SWEEP_JOB["thread"] = worker

    worker.start()
    return build_job_snapshot(include_result=False)


def start_blowdown_job(payload):
    blowdown_config = build_blowdown_config_from_payload(payload)
    cancel_event = threading.Event()

    with JOB_LOCK:
        if SWEEP_JOB["status"] in {"running", "stopping"}:
            raise RuntimeError("An analysis is already running.")
        if SWEEP_JOB["result"] is None or "best_isp_case" not in SWEEP_JOB["result"]:
            raise RuntimeError("Run a CEA sweep first so the preliminary 0D blowdown model has a seed case.")

        base_result = deepcopy(SWEEP_JOB["result"])
        seed_case = deepcopy(base_result["best_isp_case"]["case"])
        base_result["blowdown"] = build_running_response(blowdown_config, seed_case)

        job_id = SWEEP_JOB["job_id"] + 1
        total_progress = estimate_total_steps(blowdown_config)
        SWEEP_JOB["job_id"] = job_id
        SWEEP_JOB["status"] = "running"
        SWEEP_JOB["job_type"] = "blowdown"
        SWEEP_JOB["phase"] = "blowdown"
        SWEEP_JOB["message"] = base_result["blowdown"]["message"]
        SWEEP_JOB["progress_completed"] = 0
        SWEEP_JOB["progress_total"] = total_progress
        SWEEP_JOB["progress_ratio"] = 0.0
        SWEEP_JOB["started_at"] = time.time()
        SWEEP_JOB["finished_at"] = None
        SWEEP_JOB["error"] = None
        SWEEP_JOB["result"] = base_result
        SWEEP_JOB["cancel_event"] = cancel_event
        worker = threading.Thread(
            target=run_blowdown_job,
            args=(job_id, blowdown_config, seed_case, base_result, cancel_event),
            daemon=True,
        )
        SWEEP_JOB["thread"] = worker

    worker.start()
    return build_job_snapshot(include_result=False)


def preview_blowdown(payload):
    try:
        blowdown_config = build_blowdown_config_from_payload(payload)
    except Exception as exc:
        return {
            "status": "error",
            "message": "Live sizing preview needs valid inputs.",
            "error": str(exc),
        }

    with JOB_LOCK:
        if SWEEP_JOB["result"] is None or "best_isp_case" not in SWEEP_JOB["result"]:
            return {
                "status": "needs_seed",
                "message": "Run a CEA sweep first to unlock live blowdown sizing estimates from the highest-Isp seed case.",
                "error": None,
            }
        seed_case = deepcopy(SWEEP_JOB["result"]["best_isp_case"]["case"])

    return build_blowdown_preview_response(blowdown_config, seed_case)


def stop_sweep_job():
    with JOB_LOCK:
        if SWEEP_JOB["status"] not in {"running", "stopping"}:
            raise RuntimeError("No analysis is currently running.")
        SWEEP_JOB["status"] = "stopping"
        phase_label = "blowdown" if SWEEP_JOB["phase"] == "blowdown" else "CEA sweep"
        SWEEP_JOB["message"] = f"Stopping {phase_label}..."
        cancel_event = SWEEP_JOB["cancel_event"]
    if cancel_event is not None:
        cancel_event.set()
    return build_job_snapshot(include_result=False)


class UIRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = urlparse(self.path).path
        if route in {"/", "/index.html"}:
            self._serve_file(UI_DIR / "index.html", "text/html; charset=utf-8")
            return
        if route.startswith("/assets/"):
            asset_path = (UI_DIR / route.lstrip("/")).resolve()
            try:
                asset_path.relative_to(UI_DIR.resolve())
            except ValueError:
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
                return
            content_type = "application/octet-stream"
            if asset_path.suffix.lower() == ".png":
                content_type = "image/png"
            elif asset_path.suffix.lower() in {".jpg", ".jpeg"}:
                content_type = "image/jpeg"
            elif asset_path.suffix.lower() == ".svg":
                content_type = "image/svg+xml"
            self._serve_file(asset_path, content_type)
            return
        if route == "/app.js":
            self._serve_file(UI_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if route == "/styles.css":
            self._serve_file(UI_DIR / "styles.css", "text/css; charset=utf-8")
            return
        if route == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if route == "/api/default-config":
            self._write_json(build_default_ui_config(os.cpu_count() or 1))
            return
        if route == "/api/sweep-status":
            self._write_json(build_job_snapshot(include_result=True))
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self):
        route = urlparse(self.path).path
        try:
            if route == "/api/run-sweep":
                payload = self._read_json_body()
                self._write_json(start_sweep_job(payload), status=HTTPStatus.ACCEPTED)
                return
            if route == "/api/run-blowdown":
                payload = self._read_json_body()
                self._write_json(start_blowdown_job(payload), status=HTTPStatus.ACCEPTED)
                return
            if route == "/api/blowdown-preview":
                payload = self._read_json_body()
                self._write_json(preview_blowdown(payload))
                return
            if route == "/api/stop-sweep":
                self._write_json(stop_sweep_job())
                return
        except RuntimeError as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.CONFLICT)
            return
        except Exception as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format, *args):
        return

    def _read_json_body(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(content_length).decode("utf-8"))

    def _serve_file(self, path, content_type):
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        data = path.read_bytes()
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _write_json(self, payload, status=HTTPStatus.OK):
        data = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            return


def main():
    server = ThreadingHTTPServer((HOST, PORT), UIRequestHandler)
    server.daemon_threads = True
    print(f"UI available at http://{HOST}:{PORT}")
    server.serve_forever()
