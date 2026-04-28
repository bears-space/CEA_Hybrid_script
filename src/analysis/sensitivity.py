"""One-at-a-time sensitivity analysis built around the reusable 0D solver."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from src.analysis.constraints import evaluate_constraints
from src.analysis.metrics import extract_case_metrics
from src.config import build_design_config
from src.simulation.solver_0d import run_0d_case


_PARAMETER_GETTERS = {
    "tank_temperature_k": lambda cfg: cfg["nominal"]["performance"]["tank_temperature_k"],
    "fill_fraction": lambda cfg: cfg["nominal"]["blowdown"]["tank"]["initial_fill_fraction"],
    "usable_ox_fraction": lambda cfg: cfg["nominal"]["blowdown"]["tank"]["usable_oxidizer_fraction"],
    "injector_cd": lambda cfg: cfg["nominal"]["blowdown"]["injector"]["cd"],
    "regression_a": lambda cfg: cfg["nominal"]["blowdown"]["grain"]["a_reg_si"],
    "regression_n": lambda cfg: cfg["nominal"]["blowdown"]["grain"]["n_reg"],
    "cstar_efficiency": lambda cfg: cfg["nominal"]["loss_factors"]["cstar_efficiency"],
    "cf_efficiency": lambda cfg: cfg["nominal"]["loss_factors"]["cf_efficiency"],
    "usable_fuel_fraction": lambda cfg: cfg["nominal"]["blowdown"]["grain"]["fuel_usable_fraction"],
    "injector_dp_fraction": lambda cfg: cfg["nominal"]["blowdown"]["injector"]["delta_p_fraction_of_pc"],
    "line_loss_multiplier": lambda cfg: cfg["nominal"]["loss_factors"]["line_loss_multiplier"],
    "nozzle_discharge_factor": lambda cfg: cfg["nominal"]["loss_factors"]["nozzle_discharge_factor"],
}


def _set_parameter(config: dict[str, Any], parameter: str, value: float) -> None:
    nominal = config["nominal"]
    if parameter == "tank_temperature_k":
        nominal["performance"]["tank_temperature_k"] = value
        nominal["blowdown"]["tank"]["initial_temp_k"] = value
    elif parameter == "fill_fraction":
        nominal["blowdown"]["tank"]["initial_fill_fraction"] = value
    elif parameter == "usable_ox_fraction":
        nominal["blowdown"]["tank"]["usable_oxidizer_fraction"] = value
    elif parameter == "injector_cd":
        nominal["blowdown"]["injector"]["cd"] = value
    elif parameter == "regression_a":
        nominal["blowdown"]["grain"]["a_reg_si"] = value
        nominal["blowdown"]["grain"]["regression_preset"] = "custom"
    elif parameter == "regression_n":
        nominal["blowdown"]["grain"]["n_reg"] = value
        nominal["blowdown"]["grain"]["regression_preset"] = "custom"
    elif parameter == "cstar_efficiency":
        nominal["loss_factors"]["cstar_efficiency"] = value
    elif parameter == "cf_efficiency":
        nominal["loss_factors"]["cf_efficiency"] = value
    elif parameter == "usable_fuel_fraction":
        nominal["blowdown"]["grain"]["fuel_usable_fraction"] = value
    elif parameter == "injector_dp_fraction":
        nominal["blowdown"]["injector"]["delta_p_mode"] = "fraction_of_pc"
        nominal["blowdown"]["injector"]["delta_p_fraction_of_pc"] = value
    elif parameter == "line_loss_multiplier":
        nominal["loss_factors"]["line_loss_multiplier"] = value
    elif parameter == "nozzle_discharge_factor":
        nominal["loss_factors"]["nozzle_discharge_factor"] = value
    else:
        raise ValueError(f"Unsupported sensitivity parameter: {parameter}")


def _varied_value(x0: float, mode: str, magnitude: float, direction: str) -> float:
    sign = -1.0 if direction == "low" else 1.0
    if mode == "percent":
        return x0 * (1.0 + sign * magnitude)
    return x0 + sign * magnitude


def _normalized_sensitivity(y0: float, y1: float, x0: float, x1: float) -> float | None:
    if x0 == 0.0 or y0 == 0.0:
        return None
    dx_rel = (x1 - x0) / x0
    if dx_rel == 0.0:
        return None
    return ((y1 - y0) / y0) / dx_rel


def run_oat_sensitivity(config: Mapping[str, Any]) -> dict[str, Any]:
    study_config = build_design_config(config)
    nominal_result = run_0d_case(study_config)
    nominal_metrics = extract_case_metrics(nominal_result, study_config)
    nominal_constraints = evaluate_constraints(nominal_metrics, study_config["constraints"])

    oat_rows: list[dict[str, Any]] = []
    ranking_rows: dict[str, list[dict[str, Any]]] = {metric: [] for metric in study_config["sensitivity_metrics"]}

    for parameter, spec in study_config["uncertainty"].items():
        x0 = float(_PARAMETER_GETTERS[parameter](study_config))
        metric_pairs: dict[str, dict[str, Any]] = {}

        for direction in ("low", "high"):
            varied_config = deepcopy(study_config)
            x1 = _varied_value(x0, spec["mode"], float(spec["value"]), direction)
            _set_parameter(varied_config, parameter, x1)
            result = run_0d_case(varied_config)
            metrics = extract_case_metrics(result, varied_config)
            constraints = evaluate_constraints(metrics, varied_config["constraints"])
            oat_rows.append(
                {
                    "parameter": parameter,
                    "direction": direction,
                    "input_nominal": x0,
                    "input_varied": x1,
                    **metrics,
                    "constraints_all_pass": constraints["all_pass"],
                }
            )
            metric_pairs[direction] = {
                "input_value": x1,
                "metrics": metrics,
            }

        for metric_key in study_config["sensitivity_metrics"]:
            y0 = nominal_metrics.get(metric_key)
            y_low = metric_pairs["low"]["metrics"].get(metric_key)
            y_high = metric_pairs["high"]["metrics"].get(metric_key)
            s_low = None if y_low is None else _normalized_sensitivity(y0, y_low, x0, metric_pairs["low"]["input_value"])
            s_high = None if y_high is None else _normalized_sensitivity(y0, y_high, x0, metric_pairs["high"]["input_value"])
            if s_low is not None and s_high is not None and x0 != 0.0 and y0 not in {None, 0.0}:
                s_central = ((y_high - y_low) / y0) / ((metric_pairs["high"]["input_value"] - metric_pairs["low"]["input_value"]) / x0)
            else:
                candidates = [abs(value) for value in (s_low, s_high) if value is not None]
                s_central = candidates[0] if candidates else None
            ranking_rows[metric_key].append(
                {
                    "parameter": parameter,
                    "metric": metric_key,
                    "nominal_output": y0,
                    "low_output": y_low,
                    "high_output": y_high,
                    "sensitivity_low": s_low,
                    "sensitivity_high": s_high,
                    "normalized_sensitivity": s_central,
                    "normalized_sensitivity_abs": None if s_central is None else abs(s_central),
                }
            )

    for metric_key in ranking_rows:
        ranking_rows[metric_key].sort(key=lambda row: row["normalized_sensitivity_abs"] or -1.0, reverse=True)

    return {
        "nominal": {
            "result": nominal_result,
            "metrics": nominal_metrics,
            "constraints": nominal_constraints,
        },
        "cases": oat_rows,
        "rankings": ranking_rows,
        "config": study_config,
    }
