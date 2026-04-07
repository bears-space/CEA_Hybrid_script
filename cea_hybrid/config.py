"""Configuration loading and validation for sweep runs."""

import json
import math
from pathlib import Path

import numpy as np

from cea_hybrid.constants import METRIC_OPTIONS
from cea_hybrid.nozzle_sizing import (
    CAP_MODE_AREA_RATIO,
    CAP_MODE_EXIT_DIAMETER,
    build_ae_at_values,
)


def ensure_finite(value, name):
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite.")


def expand_sweep_values(spec, name):
    if isinstance(spec, list):
        values = spec
    elif isinstance(spec, dict):
        if "values" in spec:
            values = spec["values"]
        elif {"start", "stop", "count"} <= spec.keys():
            values = np.linspace(
                float(spec["start"]),
                float(spec["stop"]),
                int(spec["count"]),
            ).tolist()
        elif {"start", "stop", "step"} <= spec.keys():
            start = float(spec["start"])
            stop = float(spec["stop"])
            step = float(spec["step"])
            if step == 0.0:
                raise ValueError(f"{name} step cannot be zero.")

            values = []
            current = start
            tolerance = abs(step) * 1e-9
            if step > 0.0:
                while current <= stop + tolerance:
                    values.append(current)
                    current += step
            else:
                while current >= stop - tolerance:
                    values.append(current)
                    current += step
        else:
            raise ValueError(
                f"{name} must be a list or an object with values, "
                "start/stop/count, or start/stop/step."
            )
    else:
        raise ValueError(f"{name} must be a list or object.")

    if not values:
        raise ValueError(f"{name} cannot be empty.")
    return [float(value) for value in values]


def build_config(raw):
    sweeps = raw["sweeps"]
    abs_surrogate = raw["abs_surrogate"]
    densities = raw["densities_g_cm3"]
    species = raw["species"]

    styrene_share = float(abs_surrogate["styrene_share"])
    butadiene_share = float(abs_surrogate["butadiene_share"])
    share_total = styrene_share + butadiene_share
    if share_total <= 0.0:
        raise ValueError("ABS surrogate shares must sum to a positive value.")

    target_thrust_n = float(raw["target_thrust_n"])
    max_exit_diameter_cm = (
        float(raw["max_exit_diameter_cm"]) if raw.get("max_exit_diameter_cm") is not None else None
    )
    max_area_ratio = float(raw.get("max_area_ratio", 24.0))
    ae_at_cap_mode = raw.get("ae_at_cap_mode", CAP_MODE_EXIT_DIAMETER)
    ae_at_values = build_ae_at_values(
        sweeps["ae_at"],
        target_thrust_n,
        float(raw["pc_bar"]),
        ae_at_cap_mode,
        max_exit_diameter_cm=max_exit_diameter_cm,
        max_area_ratio=max_area_ratio,
    )

    config = {
        "target_thrust_n": target_thrust_n,
        "max_exit_diameter_cm": max_exit_diameter_cm,
        "max_area_ratio": max_area_ratio,
        "ae_at_cap_mode": ae_at_cap_mode,
        "pc_bar": float(raw["pc_bar"]),
        "iac": bool(raw.get("iac", True)),
        "cpu_workers": raw.get("cpu_workers", "auto"),
        "summary_metric": raw.get("summary_metric", "isp_vac_s"),
        "output_dir": Path(raw.get("output_dir", "outputs")),
        "plots": {
            "enabled": bool(raw.get("plots", {}).get("enabled", True)),
            "metric": raw.get("plots", {}).get(
                "metric",
                raw.get("summary_metric", "isp_vac_s"),
            ),
            "output_dir": Path(raw.get("plots", {}).get("output_dir", "plots")),
        },
        "ae_at_values": ae_at_values,
        "of_values": expand_sweep_values(sweeps["of"], "sweeps.of"),
        "abs_volume_fractions": expand_sweep_values(
            sweeps["abs_volume_fractions"],
            "sweeps.abs_volume_fractions",
        ),
        "fuel_temperatures_k": expand_sweep_values(
            sweeps["fuel_temperatures_k"],
            "sweeps.fuel_temperatures_k",
        ),
        "oxidizer_temperatures_k": expand_sweep_values(
            sweeps["oxidizer_temperatures_k"],
            "sweeps.oxidizer_temperatures_k",
        ),
        "species": {
            "oxidizer": species["oxidizer"],
            "fuel_main": species["fuel_main"],
            "styrene": species["styrene"],
            "butadiene": species["butadiene"],
        },
        "rho_paraffin": float(densities["paraffin"]),
        "rho_abs": float(densities["abs"]),
        "styrene_weight": styrene_share / share_total,
        "butadiene_weight": butadiene_share / share_total,
    }
    validate_config(config)
    return config


def load_config(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return build_config(raw)


def validate_config(config):
    ensure_finite(config["target_thrust_n"], "target_thrust_n")
    ensure_finite(config["max_area_ratio"], "max_area_ratio")
    ensure_finite(config["pc_bar"], "pc_bar")
    if config["target_thrust_n"] <= 0.0:
        raise ValueError("target_thrust_n must be positive.")
    if config["ae_at_cap_mode"] not in {CAP_MODE_EXIT_DIAMETER, CAP_MODE_AREA_RATIO}:
        raise ValueError("ae_at_cap_mode must be 'exit_diameter' or 'area_ratio'.")
    if config["ae_at_cap_mode"] == CAP_MODE_EXIT_DIAMETER:
        ensure_finite(config["max_exit_diameter_cm"], "max_exit_diameter_cm")
        if config["max_exit_diameter_cm"] <= 0.0:
            raise ValueError("max_exit_diameter_cm must be positive.")
    if config["max_area_ratio"] <= 1.0:
        raise ValueError("max_area_ratio must be greater than 1.0.")
    if config["pc_bar"] <= 0.0:
        raise ValueError("pc_bar must be positive.")
    if config["summary_metric"] not in METRIC_OPTIONS:
        raise ValueError(f"summary_metric must be one of: {', '.join(METRIC_OPTIONS)}")
    if config["plots"]["metric"] not in METRIC_OPTIONS:
        raise ValueError(f"plots.metric must be one of: {', '.join(METRIC_OPTIONS)}")

    for value in config["ae_at_values"]:
        ensure_finite(value, "Ae/At")
        if value <= 0.0:
            raise ValueError("All Ae/At values must be positive.")
    for value in config["of_values"]:
        ensure_finite(value, "O/F")
        if value <= 0.0:
            raise ValueError("All O/F values must be positive.")
    for value in config["abs_volume_fractions"]:
        ensure_finite(value, "ABS volume fraction")
        if not 0.0 <= value <= 1.0:
            raise ValueError("ABS volume fractions must be between 0.0 and 1.0.")
    for value in config["fuel_temperatures_k"] + config["oxidizer_temperatures_k"]:
        ensure_finite(value, "Temperature")
        if value <= 0.0:
            raise ValueError("All temperatures must be positive in Kelvin.")
    if config["cpu_workers"] != "auto":
        try:
            cpu_workers = int(config["cpu_workers"])
        except (TypeError, ValueError) as exc:
            raise ValueError("cpu_workers must be 'auto' or a positive integer.") from exc
        if cpu_workers <= 0:
            raise ValueError("cpu_workers must be positive.")
