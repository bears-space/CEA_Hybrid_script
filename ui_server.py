import json
import math
import threading
import time
from copy import deepcopy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from main import (
    DEFAULT_CPU_WORKERS,
    SweepCancelled,
    build_config,
    metric_label,
    run_sweep,
)


HOST = "127.0.0.1"
PORT = 8000
ROOM_TEMPERATURE_K = 293.15
ROOT_DIR = Path(__file__).parent
UI_DIR = ROOT_DIR / "ui"
INPUTS_PATH = ROOT_DIR / "inputs.json"
JOB_LOCK = threading.Lock()
OBJECTIVES = [
    {"key": "isp_vac_s", "label": "Vacuum Isp", "mode": "max"},
    {"key": "isp_s", "label": "Sea-Level Isp", "mode": "max"},
    {"key": "cf", "label": "Thrust Coefficient", "mode": "max"},
    {"key": "cstar_mps", "label": "Characteristic Velocity", "mode": "max"},
    {"key": "mdot_total_kg_s", "label": "Mass Flow", "mode": "min"},
    {"key": "dt_mm", "label": "Throat Diameter", "mode": "min"},
    {"key": "de_mm", "label": "Exit Diameter", "mode": "min"},
]
METRIC_OPTIONS = [
    "isp_vac_s",
    "isp_s",
    "cf",
    "cstar_mps",
    "mdot_total_kg_s",
    "dt_mm",
    "de_mm",
    "tc_k",
]
DEFAULT_HYBRID_DESIGN = {
    "regression_model": "literature_paraffin_n2o",
    "regression_a_mps": 1.55e-4,
    "regression_n": 0.3257,
    "port_diameter_m": 0.07,
    "burn_time_s": 8.0,
    "characteristic_length_m": 12.0,
}
REGRESSION_MODELS = {
    "literature_paraffin_n2o": {
        "label": "Literature default: Paraffin/N2O",
        "a_mps": 1.55e-4,
        "n": 0.3257,
        "description": "Paraffin/N2O literature default based on reported regression-law data; used as the default proxy for the paraffin-dominant hybrid grain.",
    },
    "manual": {
        "label": "Manual coefficients",
        "a_mps": None,
        "n": None,
        "description": "User-provided regression coefficients override the literature default.",
    },
}
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


def ensure_finite(value, name):
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite.")


def _expand_raw_range(spec):
    if "values" in spec:
        return spec["values"]
    if {"start", "stop", "step"} <= spec.keys():
        values = []
        current = float(spec["start"])
        stop = float(spec["stop"])
        step = float(spec["step"])
        tolerance = abs(step) * 1e-9
        while current <= stop + tolerance:
            values.append(current)
            current += step
        return values
    if {"start", "stop", "count"} <= spec.keys():
        count = int(spec["count"])
        if count == 1:
            return [float(spec["start"])]
        start = float(spec["start"])
        stop = float(spec["stop"])
        step = (stop - start) / (count - 1)
        return [start + index * step for index in range(count)]
    raise ValueError("Unsupported sweep specification.")


def detect_range(values):
    values = [float(value) for value in values]
    if len(values) < 2:
        return {"start": values[0], "stop": values[0], "step": 1.0}

    step = values[1] - values[0]
    for index in range(2, len(values)):
        if abs((values[index] - values[index - 1]) - step) > 1e-9:
            return {"values": values}

    return {"start": values[0], "stop": values[-1], "step": step}


def load_base_raw_config():
    return json.loads(INPUTS_PATH.read_text(encoding="utf-8"))


def build_default_ui_config():
    raw = load_base_raw_config()
    raw_metric = raw.get("plots", {}).get("metric", raw.get("summary_metric", "isp_vac_s"))
    objective_metric = raw_metric if raw_metric in METRIC_OPTIONS else "isp_vac_s"
    temperature_options = sorted(
        {
            *[float(value) for value in raw["sweeps"]["fuel_temperatures_k"]],
            *[float(value) for value in raw["sweeps"]["oxidizer_temperatures_k"]],
            ROOM_TEMPERATURE_K,
        }
    )

    return {
        "target_thrust_n": raw["target_thrust_n"],
        "pc_bar": raw["pc_bar"],
        "objective_metric": objective_metric,
        "desired_infill_percent": 10.0,
        "reactant_temperature_k": min(
            temperature_options,
            key=lambda value: abs(value - ROOM_TEMPERATURE_K),
        ),
        "reactant_temperature_options": temperature_options,
        "cpu_workers": DEFAULT_CPU_WORKERS,
        "ae_at": detect_range(_expand_raw_range(raw["sweeps"]["ae_at"])),
        "of": {
            "start": raw["sweeps"]["of"]["start"],
            "stop": raw["sweeps"]["of"]["stop"],
            "count": raw["sweeps"]["of"]["count"],
        },
        "hybrid_design": deepcopy(DEFAULT_HYBRID_DESIGN),
        "regression_models": [
            {"key": key, "label": value["label"], "description": value["description"]}
            for key, value in REGRESSION_MODELS.items()
        ],
        "metric_options": [{"key": key, "label": metric_label(key)} for key in METRIC_OPTIONS],
    }


def build_raw_config_from_payload(payload):
    raw = deepcopy(load_base_raw_config())
    reactant_temperature_k = float(payload["reactant_temperature_k"])
    desired_infill_percent = float(payload["desired_infill_percent"])
    ensure_finite(payload["target_thrust_n"], "Target thrust")
    ensure_finite(payload["pc_bar"], "Chamber pressure")
    ensure_finite(reactant_temperature_k, "Reactant temperature")
    ensure_finite(desired_infill_percent, "Desired infill")
    for name, value in [
        ("Ae/At start", payload["ae_at"]["start"]),
        ("Ae/At stop", payload["ae_at"]["stop"]),
        ("Ae/At step", payload["ae_at"]["step"]),
        ("O/F start", payload["of"]["start"]),
        ("O/F stop", payload["of"]["stop"]),
        ("O/F count", payload["of"]["count"]),
    ]:
        ensure_finite(value, name)
    if reactant_temperature_k <= 0.0:
        raise ValueError("Reactant temperature must be positive in Kelvin.")
    if not 0.0 <= desired_infill_percent <= 100.0:
        raise ValueError("Desired infill must be between 0 and 100 percent.")

    raw["target_thrust_n"] = float(payload["target_thrust_n"])
    raw["pc_bar"] = float(payload["pc_bar"])
    raw["summary_metric"] = payload["objective_metric"]
    raw["plots"]["metric"] = payload["objective_metric"]
    raw["plots"]["enabled"] = False
    raw["sweeps"]["ae_at"] = {
        "start": float(payload["ae_at"]["start"]),
        "stop": float(payload["ae_at"]["stop"]),
        "step": float(payload["ae_at"]["step"]),
    }
    raw["sweeps"]["of"] = {
        "start": float(payload["of"]["start"]),
        "stop": float(payload["of"]["stop"]),
        "count": int(payload["of"]["count"]),
    }
    raw["sweeps"]["abs_volume_fractions"] = [desired_infill_percent / 100.0]
    raw["sweeps"]["fuel_temperatures_k"] = [reactant_temperature_k]
    raw["sweeps"]["oxidizer_temperatures_k"] = [reactant_temperature_k]
    return raw


def extract_hybrid_design_config(payload):
    design = deepcopy(DEFAULT_HYBRID_DESIGN)
    design.update(payload.get("hybrid_design", {}))
    design["regression_model"] = str(design["regression_model"])
    design["regression_a_mps"] = float(design["regression_a_mps"])
    design["regression_n"] = float(design["regression_n"])
    design["port_diameter_m"] = float(design["port_diameter_m"])
    design["burn_time_s"] = float(design["burn_time_s"])
    design["characteristic_length_m"] = float(design["characteristic_length_m"])
    for name, value in [
        ("Regression coefficient a", design["regression_a_mps"]),
        ("Regression exponent n", design["regression_n"]),
        ("Port diameter D_p", design["port_diameter_m"]),
        ("Burn time", design["burn_time_s"]),
        ("Characteristic length", design["characteristic_length_m"]),
    ]:
        ensure_finite(value, name)

    if design["regression_model"] not in REGRESSION_MODELS:
        raise ValueError("Unknown regression model selected.")
    if design["port_diameter_m"] <= 0.0:
        raise ValueError("Port diameter D_p must be positive.")
    if design["burn_time_s"] <= 0.0:
        raise ValueError("Burn time must be positive.")
    if design["characteristic_length_m"] <= 0.0:
        raise ValueError("Characteristic length must be positive.")
    if design["regression_model"] == "manual":
        if design["regression_a_mps"] <= 0.0:
            raise ValueError("Hybrid regression coefficient a must be positive.")
        if design["regression_n"] <= 0.0:
            raise ValueError("Hybrid regression exponent n must be positive.")
    else:
        model = REGRESSION_MODELS[design["regression_model"]]
        design["regression_a_mps"] = model["a_mps"]
        design["regression_n"] = model["n"]
    return design


def compact_case(case, keys):
    return {key: case[key] for key in keys}


def density_from_infill(abs_vol_frac, rho_abs_g_cm3, rho_paraffin_g_cm3):
    rho_abs = rho_abs_g_cm3 * 1000.0
    rho_paraffin = rho_paraffin_g_cm3 * 1000.0
    return abs_vol_frac * rho_abs + (1.0 - abs_vol_frac) * rho_paraffin


def build_hybrid_design(case, config, design):
    pc_pa = case["pc_bar"] * 1e5
    thrust_from_cf_n = case["cf"] * pc_pa * case["at_m2"]
    cstar_from_flow_mps = (pc_pa * case["at_m2"]) / case["mdot_total_kg_s"]

    mdot_total = case["mdot_total_kg_s"]
    of_ratio = case["of"]
    mdot_ox = mdot_total * of_ratio / (1.0 + of_ratio)
    mdot_f_total = mdot_total / (1.0 + of_ratio)
    port_diameter_m = design["port_diameter_m"]
    gox = (4.0 * mdot_ox) / (math.pi * port_diameter_m ** 2)
    regression_rate_mps = design["regression_a_mps"] * (gox ** design["regression_n"])
    fuel_density_kg_m3 = density_from_infill(
        case["abs_vol_frac"],
        config["rho_abs"],
        config["rho_paraffin"],
    )
    grain_length_m = mdot_f_total / (
        fuel_density_kg_m3 * math.pi * port_diameter_m * regression_rate_mps
    )
    mdot_f_regression = fuel_density_kg_m3 * math.pi * port_diameter_m * grain_length_m * regression_rate_mps
    of_check = mdot_ox / mdot_f_regression
    port_diameter_rate_mps = 2.0 * regression_rate_mps
    burn_time_s = design["burn_time_s"]
    growth_constant = 2.0 * design["regression_a_mps"] * ((4.0 * mdot_ox) / math.pi) ** design["regression_n"]
    exponent = 2.0 * design["regression_n"] + 1.0
    final_port_diameter_m = (
        port_diameter_m ** exponent + exponent * growth_constant * burn_time_s
    ) ** (1.0 / exponent)
    chamber_inner_diameter_m = final_port_diameter_m
    web_thickness_m = 0.5 * (final_port_diameter_m - port_diameter_m)
    volumetric_loading = 1.0 - (port_diameter_m / chamber_inner_diameter_m) ** 2
    fuel_mass_total_kg = (
        fuel_density_kg_m3
        * (math.pi / 4.0)
        * (chamber_inner_diameter_m ** 2 - port_diameter_m ** 2)
        * grain_length_m
    )
    average_port_diameter_m = 0.5 * (port_diameter_m + final_port_diameter_m)
    average_port_area_m2 = math.pi * average_port_diameter_m ** 2 / 4.0
    chamber_cross_section_area_m2 = math.pi * chamber_inner_diameter_m ** 2 / 4.0
    pre_chamber_length_m = chamber_inner_diameter_m
    target_characteristic_volume_m3 = design["characteristic_length_m"] * case["at_m2"]
    port_volume_m3 = average_port_area_m2 * grain_length_m
    pre_chamber_volume_m3 = chamber_cross_section_area_m2 * pre_chamber_length_m
    minimum_characteristic_length_m = (
        port_volume_m3 + pre_chamber_volume_m3
    ) / case["at_m2"]
    remaining_post_volume_m3 = max(
        0.0,
        target_characteristic_volume_m3 - port_volume_m3 - pre_chamber_volume_m3,
    )
    post_chamber_length_m = remaining_post_volume_m3 / chamber_cross_section_area_m2
    total_chamber_length_m = pre_chamber_length_m + grain_length_m + post_chamber_length_m
    chamber_volume_m3 = pre_chamber_volume_m3 + port_volume_m3 + remaining_post_volume_m3
    achieved_characteristic_length_m = chamber_volume_m3 / case["at_m2"]
    for name, value in [
        ("Gox", gox),
        ("Regression rate", regression_rate_mps),
        ("Grain length", grain_length_m),
        ("Final port diameter", final_port_diameter_m),
        ("Fuel mass", fuel_mass_total_kg),
        ("Achieved characteristic length", achieved_characteristic_length_m),
    ]:
        ensure_finite(value, name)
        if value < 0.0:
            raise ValueError(f"{name} must be non-negative.")

    return {
        "equations": {
            "thrust_from_cf_n": thrust_from_cf_n,
            "cstar_from_flow_mps": cstar_from_flow_mps,
            "mdot_total_kg_s": mdot_total,
            "mdot_ox_kg_s": mdot_ox,
            "mdot_f_total_kg_s": mdot_f_total,
            "gox_kg_m2_s": gox,
            "regression_rate_mps": regression_rate_mps,
            "mdot_f_regression_kg_s": mdot_f_regression,
            "of_check": of_check,
            "d_port_dt_mps": port_diameter_rate_mps,
        },
        "geometry": {
            "fuel_density_kg_m3": fuel_density_kg_m3,
            "port_diameter_m": port_diameter_m,
            "final_port_diameter_m": final_port_diameter_m,
            "grain_length_m": grain_length_m,
            "chamber_inner_diameter_m": chamber_inner_diameter_m,
            "web_thickness_m": web_thickness_m,
            "burn_time_s": burn_time_s,
            "fuel_mass_total_kg": fuel_mass_total_kg,
            "average_port_area_m2": average_port_area_m2,
            "volumetric_loading": volumetric_loading,
            "pre_chamber_length_m": pre_chamber_length_m,
            "post_chamber_length_m": post_chamber_length_m,
            "total_chamber_length_m": total_chamber_length_m,
            "chamber_volume_m3": chamber_volume_m3,
            "characteristic_length_target_m": design["characteristic_length_m"],
            "characteristic_length_minimum_m": minimum_characteristic_length_m,
            "characteristic_length_achieved_m": achieved_characteristic_length_m,
        },
        "assumptions": {
            "regression_model": design["regression_model"],
            "regression_model_label": REGRESSION_MODELS[design["regression_model"]]["label"],
            "regression_model_description": REGRESSION_MODELS[design["regression_model"]]["description"],
            "regression_a_mps": design["regression_a_mps"],
            "regression_n": design["regression_n"],
            "port_diameter_m": design["port_diameter_m"],
            "burn_time_s": design["burn_time_s"],
            "characteristic_length_m": design["characteristic_length_m"],
            "pre_chamber_method": "Empirical axial showerhead estimate: L_pre = D_c",
            "post_chamber_method": "Solved from target characteristic length using average port area over the burn.",
        },
    }


def build_ui_response(config, sweep_results, runtime_seconds, hybrid_design):
    objective_metric = config["summary_metric"]
    cases = sweep_results["cases"]
    if not cases:
        raise ValueError("No converged cases were produced for the selected settings.")
    best_by_ae_at = sorted(sweep_results["best_by_ae_at"], key=lambda row: row["ae_at"])
    reactant_temperature_k = config["fuel_temperatures_k"][0]
    desired_infill_percent = config["abs_volume_fractions"][0] * 100.0

    raw_by_ae_at = {}
    for row in cases:
        raw_by_ae_at.setdefault(row["ae_at"], []).append(row)

    raw_series = []
    for ae_at, rows in sorted(raw_by_ae_at.items()):
        sorted_rows = sorted(rows, key=lambda row: row["of"])
        raw_series.append(
            {
                "label": f"Ae/At {ae_at:g}",
                "ae_at": ae_at,
                "points": [
                    {
                        "x": row["of"],
                        "y": row[objective_metric],
                        "of": row["of"],
                        "ae_at": row["ae_at"],
                    }
                    for row in sorted_rows
                ],
            }
        )

    objective_points = [{"x": row["ae_at"], "y": row[objective_metric], "of": row["of"]} for row in best_by_ae_at]
    best_of_points = [{"x": row["ae_at"], "y": row["of"], "objective": row[objective_metric]} for row in best_by_ae_at]

    optimizations = []
    for objective in OBJECTIVES:
        key = objective["key"]
        best_case = (
            max(cases, key=lambda case: case[key])
            if objective["mode"] == "max"
            else min(cases, key=lambda case: case[key])
        )
        optimizations.append(
            {
                "objective": objective["label"],
                "key": key,
                "mode": objective["mode"],
                "value_label": metric_label(key),
                "value": best_case[key],
                "case": compact_case(
                    best_case,
                    [
                        "abs_vol_frac",
                        "fuel_temp_k",
                        "oxidizer_temp_k",
                        "of",
                        "ae_at",
                        "isp_s",
                        "isp_vac_s",
                        "cf",
                        "cstar_mps",
                        "mdot_total_kg_s",
                        "dt_mm",
                        "de_mm",
                        "tc_k",
                    ],
                ),
                "hybrid_design": build_hybrid_design(best_case, config, hybrid_design),
            }
        )

    return {
        "meta": {
            "objective_metric": objective_metric,
            "objective_metric_label": metric_label(objective_metric),
            "case_count": len(cases),
            "failure_count": len(sweep_results["failures"]),
            "total_combinations": sweep_results["total_combinations"],
            "runtime_seconds": runtime_seconds,
            "cpu_workers": sweep_results["cpu_workers"],
            "backend": sweep_results["backend"],
            "gpu_enabled": sweep_results["gpu_enabled"],
        },
        "controls": {
            "reactant_temperature_k": reactant_temperature_k,
            "desired_infill_percent": desired_infill_percent,
            "ae_at_values": config["ae_at_values"],
            "of_values": config["of_values"],
        },
        "charts": {
            "raw_objective_by_ae_at": raw_series,
            "best_objective_by_ae_at": {
                "label": f"Best {metric_label(objective_metric)}",
                "points": objective_points,
            },
            "best_of_by_ae_at": {
                "label": "Best O/F",
                "points": best_of_points,
            },
        },
        "optimizations": optimizations,
    }


def count_total_combinations(config):
    return (
        len(config["abs_volume_fractions"])
        * len(config["fuel_temperatures_k"])
        * len(config["oxidizer_temperatures_k"])
        * len(config["ae_at_values"])
        * len(config["of_values"])
    )


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


def run_sweep_job(job_id, config, hybrid_design, cancel_event):
    started_at = time.perf_counter()
    try:
        sweep_results = run_sweep(
            config,
            progress_callback=lambda completed, total: update_job_progress(job_id, completed, total),
            cancel_event=cancel_event,
        )
        runtime_seconds = time.perf_counter() - started_at
        response = build_ui_response(config, sweep_results, runtime_seconds, hybrid_design)
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
    raw_config = build_raw_config_from_payload(payload)
    config = build_config(raw_config)
    hybrid_design = extract_hybrid_design_config(payload)
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
            args=(job_id, config, hybrid_design, cancel_event),
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
            self._write_json(build_default_ui_config())
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


if __name__ == "__main__":
    main()
