"""Configuration defaults and loaders for the Step 1 design-study workflow."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from project_data import load_project_defaults
from src.constants import DEFAULT_SENSITIVITY_METRICS, SUPPORTED_UNCERTAINTY_PARAMETERS
from src.io_utils import deep_merge, load_json


@dataclass(frozen=True)
class UncertaintySpec:
    mode: str
    value: float


@dataclass(frozen=True)
class CornerCaseDefinition:
    name: str
    adjustments: dict[str, Any]


DEFAULT_DESIGN_CONFIG: dict[str, Any] = deepcopy(load_project_defaults()["design_workflow"])


def _validate_uncertainty_section(section: Mapping[str, Any]) -> dict[str, UncertaintySpec]:
    validated: dict[str, UncertaintySpec] = {}
    for key, raw_spec in section.items():
        if key not in SUPPORTED_UNCERTAINTY_PARAMETERS:
            raise ValueError(f"Unsupported uncertainty parameter: {key}")
        mode = str(raw_spec["mode"]).lower()
        if mode not in {"percent", "absolute"}:
            raise ValueError(f"Uncertainty mode for {key} must be 'percent' or 'absolute'.")
        value = float(raw_spec["value"])
        if value < 0.0:
            raise ValueError(f"Uncertainty magnitude for {key} must be non-negative.")
        validated[key] = UncertaintySpec(mode=mode, value=value)
    return validated


def _derived_default_constraints(config: dict[str, Any]) -> dict[str, Any]:
    target_thrust_n = float(config["nominal"]["performance"]["target_thrust_n"])
    burn_time_s = float(config["nominal"]["blowdown"]["simulation"]["burn_time_s"])
    return {
        "pc_peak_bar": {"max": 60.0},
        "pc_avg_bar": {"min": 10.0},
        "thrust_avg_n": {"min": 0.75 * target_thrust_n},
        "thrust_peak_n": {"max": 1.50 * target_thrust_n},
        "of_avg": {"min": 2.0, "max": 12.0},
        "burn_time_actual_s": {"min": 0.8 * burn_time_s, "max": 1.2 * burn_time_s},
        "status": {"allowed": ["completed"]},
    }


def _normalize_geometry_policy(section: Mapping[str, Any]) -> dict[str, Any]:
    policy = deepcopy(dict(section))
    policy["baseline_port_count"] = int(policy.get("baseline_port_count", 1))
    if policy["baseline_port_count"] <= 0:
        raise ValueError("geometry_policy.baseline_port_count must be positive.")

    for key in (
        "single_port_baseline",
        "prechamber_enabled",
        "postchamber_enabled",
        "axial_showerhead_injector_baseline",
        "injector_discharges_to_prechamber",
        "lstar_report_only",
        "require_nominal_constraints_pass",
        "require_corner_constraints_pass",
        "use_nominal_case_for_cea_reference",
    ):
        if key in policy:
            policy[key] = bool(policy[key])

    for key in (
        "grain_to_chamber_radial_clearance_m",
        "injector_face_margin_factor",
        "max_injector_face_margin_factor",
        "prechamber_length_fraction_of_grain",
        "postchamber_length_fraction_of_grain",
        "injector_plate_thickness_m",
        "chamber_wall_thickness_guess_m",
        "min_radial_web_m",
        "min_nozzle_area_ratio",
        "max_nozzle_area_ratio",
        "min_chamber_to_throat_diameter_ratio",
        "max_chamber_to_throat_diameter_ratio",
        "min_port_to_throat_diameter_ratio",
        "max_port_to_throat_diameter_ratio",
        "lstar_warning_min_m",
        "lstar_warning_max_m",
    ):
        if key in policy and policy[key] is not None:
            policy[key] = float(policy[key])

    if policy["injector_face_margin_factor"] < 1.0:
        raise ValueError("geometry_policy.injector_face_margin_factor must be >= 1.0.")
    if policy["max_injector_face_margin_factor"] < policy["injector_face_margin_factor"]:
        raise ValueError("geometry_policy.max_injector_face_margin_factor must be >= injector_face_margin_factor.")
    return policy


def build_design_config(raw: Mapping[str, Any] | None = None) -> dict[str, Any]:
    config = deep_merge(DEFAULT_DESIGN_CONFIG, raw or {})
    config["uncertainty"] = {
        key: {"mode": spec.mode, "value": spec.value}
        for key, spec in _validate_uncertainty_section(config.get("uncertainty", {})).items()
    }
    config["constraints"] = deep_merge(_derived_default_constraints(config), config.get("constraints", {}))
    config["sensitivity_metrics"] = [str(metric) for metric in config.get("sensitivity_metrics", DEFAULT_SENSITIVITY_METRICS)]
    if not config["sensitivity_metrics"]:
        raise ValueError("At least one sensitivity metric is required.")
    config["geometry_policy"] = _normalize_geometry_policy(config.get("geometry_policy", {}))
    config["nominal"]["blowdown"]["ui_mode"] = config["nominal"]["blowdown"].get("ui_mode", "advanced")
    config["nominal"]["blowdown"]["tank"]["initial_temp_k"] = float(
        config["nominal"]["performance"]["tank_temperature_k"]
    )
    return config


def load_design_config(path: str | Path) -> dict[str, Any]:
    return build_design_config(load_json(path))
