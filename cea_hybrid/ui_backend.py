"""UI-facing payload builders for CEA-only sweep results."""

import json

from cea_hybrid.config import build_config, ensure_finite
from cea_hybrid.constants import (
    CASE_FIELDS,
    INPUTS_PATH,
    METRIC_OPTIONS,
    ROOM_TEMPERATURE_K,
)
from cea_hybrid.labels import metric_label
from cea_hybrid.nozzle_sizing import CAP_MODE_AREA_RATIO, CAP_MODE_EXIT_DIAMETER


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


def build_default_ui_config(default_cpu_workers):
    raw = load_base_raw_config()
    raw_metric = raw.get("plots", {}).get("metric", raw.get("summary_metric", "isp_vac_s"))
    selected_metric = raw_metric if raw_metric in METRIC_OPTIONS else "isp_vac_s"
    temperature_options = sorted(
        {
            *[float(value) for value in raw["sweeps"]["fuel_temperatures_k"]],
            *[float(value) for value in raw["sweeps"]["oxidizer_temperatures_k"]],
            ROOM_TEMPERATURE_K,
        }
    )

    default_temperature_k = min(
        temperature_options,
        key=lambda value: abs(value - ROOM_TEMPERATURE_K),
    )

    return {
        "target_thrust_n": raw["target_thrust_n"],
        "max_exit_diameter_cm": raw["max_exit_diameter_cm"],
        "max_area_ratio": raw.get("max_area_ratio", 24.0),
        "ae_at_cap_mode": raw.get("ae_at_cap_mode", CAP_MODE_EXIT_DIAMETER),
        "pc_bar": raw["pc_bar"],
        "selected_metric": selected_metric,
        "desired_infill_percent": 10.0,
        "fuel_temperature_k": default_temperature_k,
        "oxidizer_temperature_k": default_temperature_k,
        "reactant_temperature_k": default_temperature_k,
        "reactant_temperature_options": temperature_options,
        "cpu_workers": default_cpu_workers,
        "ae_at": {
            "custom_enabled": bool(raw["sweeps"]["ae_at"].get("custom_enabled", False)),
            "start": raw["sweeps"]["ae_at"].get("start", 1.0),
            "stop": raw["sweeps"]["ae_at"].get("stop", raw.get("max_area_ratio", 24.0)),
            "step": raw["sweeps"]["ae_at"].get("step", 1.0),
            "cf_search_upper_bound": raw["sweeps"]["ae_at"].get("cf_search_upper_bound", 3.0),
        },
        "of": {
            "start": raw["sweeps"]["of"]["start"],
            "stop": raw["sweeps"]["of"]["stop"],
            "count": raw["sweeps"]["of"]["count"],
        },
        "metric_options": [{"key": key, "label": metric_label(key)} for key in METRIC_OPTIONS],
    }


def build_raw_config_from_payload(payload):
    raw = load_base_raw_config()
    fuel_temperature_k = float(payload.get("fuel_temperature_k", payload.get("reactant_temperature_k")))
    oxidizer_temperature_k = float(payload.get("oxidizer_temperature_k", payload.get("reactant_temperature_k")))
    desired_infill_percent = float(payload["desired_infill_percent"])

    ensure_finite(payload["target_thrust_n"], "Target thrust")
    ensure_finite(payload["max_area_ratio"], "Maximum area ratio")
    ensure_finite(payload["pc_bar"], "Chamber pressure")
    ensure_finite(fuel_temperature_k, "Fuel temperature")
    ensure_finite(oxidizer_temperature_k, "Oxidizer temperature")
    ensure_finite(desired_infill_percent, "Desired infill")
    for name, value in [
        ("Ae/At start", payload["ae_at"].get("start", 1.0)),
        ("Ae/At stop", payload["ae_at"].get("stop", payload["max_area_ratio"])),
        ("Ae/At step", payload["ae_at"]["step"]),
        ("O/F start", payload["of"]["start"]),
        ("O/F stop", payload["of"]["stop"]),
        ("O/F count", payload["of"]["count"]),
    ]:
        ensure_finite(value, name)

    if fuel_temperature_k <= 0.0:
        raise ValueError("Fuel temperature must be positive in Kelvin.")
    if oxidizer_temperature_k <= 0.0:
        raise ValueError("Oxidizer temperature must be positive in Kelvin.")
    if not 0.0 <= desired_infill_percent <= 100.0:
        raise ValueError("Desired infill must be between 0 and 100 percent.")
    if float(payload["target_thrust_n"]) <= 0.0:
        raise ValueError("Target thrust must be positive.")
    if payload["ae_at_cap_mode"] not in {CAP_MODE_EXIT_DIAMETER, CAP_MODE_AREA_RATIO}:
        raise ValueError("Unknown Ae/At cap mode.")
    if payload["ae_at_cap_mode"] == CAP_MODE_EXIT_DIAMETER:
        ensure_finite(payload["max_exit_diameter_cm"], "Maximum exit diameter")
        if float(payload["max_exit_diameter_cm"]) <= 0.0:
            raise ValueError("Maximum exit diameter must be positive.")
    if float(payload["max_area_ratio"]) <= 1.0:
        raise ValueError("Maximum area ratio must be greater than 1.")
    if payload["selected_metric"] not in METRIC_OPTIONS:
        raise ValueError("Unknown plot metric.")

    raw["target_thrust_n"] = float(payload["target_thrust_n"])
    raw["max_exit_diameter_cm"] = float(payload["max_exit_diameter_cm"])
    raw["max_area_ratio"] = float(payload["max_area_ratio"])
    raw["ae_at_cap_mode"] = payload["ae_at_cap_mode"]
    raw["pc_bar"] = float(payload["pc_bar"])
    raw["summary_metric"] = payload["selected_metric"]
    raw["plots"]["metric"] = payload["selected_metric"]
    raw["plots"]["enabled"] = False
    raw["sweeps"]["ae_at"] = {
        "custom_enabled": bool(payload["ae_at"].get("custom_enabled", False)),
        "start": float(payload["ae_at"].get("start", 1.0)),
        "stop": float(payload["ae_at"].get("stop", payload["max_area_ratio"])),
        "step": float(payload["ae_at"]["step"]),
        "cf_search_upper_bound": float(payload["ae_at"].get("cf_search_upper_bound", 3.0)),
    }
    raw["sweeps"]["of"] = {
        "start": float(payload["of"]["start"]),
        "stop": float(payload["of"]["stop"]),
        "count": int(payload["of"]["count"]),
    }
    raw["sweeps"]["abs_volume_fractions"] = [desired_infill_percent / 100.0]
    raw["sweeps"]["fuel_temperatures_k"] = [fuel_temperature_k]
    raw["sweeps"]["oxidizer_temperatures_k"] = [oxidizer_temperature_k]
    return build_config(raw)


def compact_case(case, keys):
    return {key: case[key] for key in keys}


def build_case_field_list(case):
    return [
        {
            "key": key,
            "label": metric_label(key),
            "value": case[key],
        }
        for key in CASE_FIELDS
    ]


def build_ui_response(config, sweep_results, runtime_seconds):
    selected_metric = config["summary_metric"]
    cases = sweep_results["cases"]
    if not cases:
        raise ValueError("No converged cases were produced for the selected settings.")

    fuel_temperature_k = config["fuel_temperatures_k"][0]
    oxidizer_temperature_k = config["oxidizer_temperatures_k"][0]
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
                    {"x": row["of"], "y": row[selected_metric], "of": row["of"], "ae_at": row["ae_at"]}
                    for row in sorted_rows
                ],
            }
        )

    best_isp_case = max(cases, key=lambda row: row["isp_s"])

    return {
        "meta": {
            "selected_metric": selected_metric,
            "selected_metric_label": metric_label(selected_metric),
            "case_count": len(cases),
            "failure_count": len(sweep_results["failures"]),
            "total_combinations": sweep_results["total_combinations"],
            "runtime_seconds": runtime_seconds,
            "cpu_workers": sweep_results["cpu_workers"],
            "backend": sweep_results["backend"],
            "gpu_enabled": sweep_results["gpu_enabled"],
        },
        "controls": {
            "fuel_temperature_k": fuel_temperature_k,
            "oxidizer_temperature_k": oxidizer_temperature_k,
            "reactant_temperature_k": fuel_temperature_k,
            "desired_infill_percent": desired_infill_percent,
            "ae_at_values": config["ae_at_values"],
            "of_values": config["of_values"],
            "target_thrust_n": config["target_thrust_n"],
            "max_exit_diameter_cm": config["max_exit_diameter_cm"],
            "max_area_ratio": config["max_area_ratio"],
            "ae_at_cap_mode": config["ae_at_cap_mode"],
        },
        "charts": {
            "raw_metric_by_ae_at": raw_series,
        },
        "best_isp_case": {
            "message": "This output box is optimized for Isp.",
            "metric": "isp_s",
            "metric_label": metric_label("isp_s"),
            "case": compact_case(best_isp_case, CASE_FIELDS),
            "fields": build_case_field_list(best_isp_case),
        },
        "cases": [compact_case(case, CASE_FIELDS) for case in cases],
    }
