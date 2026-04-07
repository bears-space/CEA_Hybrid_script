"""HTTP server and sweep job state for the browser UI."""

import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from cea_hybrid.constants import DEFAULT_CPU_WORKERS, UI_DIR
from cea_hybrid.sweep import SweepCancelled, count_total_combinations, run_sweep
from cea_hybrid.ui_backend import (
    build_default_ui_config,
    build_raw_config_from_payload,
    build_ui_response,
)


HOST = "127.0.0.1"
PORT = 8000
JOB_LOCK = threading.Lock()
SWEEP_JOB = {
    "job_id": 0,
    "status": "idle",
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


def update_job_progress(job_id, completed, total):
    with JOB_LOCK:
        if SWEEP_JOB["job_id"] != job_id or SWEEP_JOB["status"] not in {"running", "stopping"}:
            return
        SWEEP_JOB["progress_completed"] = int(completed)
        SWEEP_JOB["progress_total"] = int(total)
        SWEEP_JOB["progress_ratio"] = 0.0 if total <= 0 else max(0.0, min(1.0, completed / total))
        if SWEEP_JOB["status"] == "running":
            SWEEP_JOB["message"] = f"Running sweep {completed}/{total}..."
        else:
            SWEEP_JOB["message"] = f"Stopping sweep {completed}/{total}..."


def run_sweep_job(job_id, config, cancel_event):
    started_at = time.perf_counter()
    try:
        sweep_results = run_sweep(
            config,
            progress_callback=lambda completed, total: update_job_progress(job_id, completed, total),
            cancel_event=cancel_event,
        )
        runtime_seconds = time.perf_counter() - started_at
        response = build_ui_response(config, sweep_results, runtime_seconds)
        with JOB_LOCK:
            if SWEEP_JOB["job_id"] != job_id:
                return
            SWEEP_JOB["status"] = "completed"
            SWEEP_JOB["message"] = "Sweep complete."
            SWEEP_JOB["progress_completed"] = sweep_results["total_combinations"]
            SWEEP_JOB["progress_total"] = sweep_results["total_combinations"]
            SWEEP_JOB["progress_ratio"] = 1.0
            SWEEP_JOB["finished_at"] = time.time()
            SWEEP_JOB["error"] = None
            SWEEP_JOB["result"] = response
            SWEEP_JOB["thread"] = None
            SWEEP_JOB["cancel_event"] = None
    except SweepCancelled:
        with JOB_LOCK:
            if SWEEP_JOB["job_id"] != job_id:
                return
            SWEEP_JOB["status"] = "cancelled"
            SWEEP_JOB["message"] = "Sweep cancelled."
            SWEEP_JOB["finished_at"] = time.time()
            SWEEP_JOB["error"] = None
            SWEEP_JOB["result"] = None
            SWEEP_JOB["thread"] = None
            SWEEP_JOB["cancel_event"] = None
    except Exception as exc:
        with JOB_LOCK:
            if SWEEP_JOB["job_id"] != job_id:
                return
            SWEEP_JOB["status"] = "error"
            SWEEP_JOB["message"] = "Sweep failed."
            SWEEP_JOB["finished_at"] = time.time()
            SWEEP_JOB["error"] = str(exc)
            SWEEP_JOB["result"] = None
            SWEEP_JOB["thread"] = None
            SWEEP_JOB["cancel_event"] = None


def start_sweep_job(payload):
    config = build_raw_config_from_payload(payload)
    total_combinations = count_total_combinations(config)
    cancel_event = threading.Event()

    with JOB_LOCK:
        if SWEEP_JOB["status"] in {"running", "stopping"}:
            raise RuntimeError("A sweep is already running.")
        job_id = SWEEP_JOB["job_id"] + 1
        SWEEP_JOB["job_id"] = job_id
        SWEEP_JOB["status"] = "running"
        SWEEP_JOB["message"] = f"Running sweep 0/{total_combinations}..."
        SWEEP_JOB["progress_completed"] = 0
        SWEEP_JOB["progress_total"] = total_combinations
        SWEEP_JOB["progress_ratio"] = 0.0
        SWEEP_JOB["started_at"] = time.time()
        SWEEP_JOB["finished_at"] = None
        SWEEP_JOB["error"] = None
        SWEEP_JOB["result"] = None
        SWEEP_JOB["cancel_event"] = cancel_event
        worker = threading.Thread(
            target=run_sweep_job,
            args=(job_id, config, cancel_event),
            daemon=True,
        )
        SWEEP_JOB["thread"] = worker

    worker.start()
    return build_job_snapshot(include_result=False)


def stop_sweep_job():
    with JOB_LOCK:
        if SWEEP_JOB["status"] not in {"running", "stopping"}:
            raise RuntimeError("No sweep is currently running.")
        SWEEP_JOB["status"] = "stopping"
        SWEEP_JOB["message"] = (
            f"Stopping sweep {SWEEP_JOB['progress_completed']}/{SWEEP_JOB['progress_total']}..."
        )
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
            self._write_json(build_default_ui_config(DEFAULT_CPU_WORKERS))
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
