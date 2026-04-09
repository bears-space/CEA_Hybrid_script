"""Named corner-case analysis built around the same reusable 0D solver."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from src.analysis.constraints import evaluate_constraints
from src.analysis.metrics import extract_case_metrics
from src.analysis.sensitivity import _set_parameter, _varied_value
from src.config_schema import build_design_config
from src.simulation.solver_0d import run_0d_case


def run_corner_cases(config: Mapping[str, Any]) -> dict[str, Any]:
    study_config = build_design_config(config)
    nominal_result = run_0d_case(study_config)
    nominal_metrics = extract_case_metrics(nominal_result, study_config)
    nominal_constraints = evaluate_constraints(nominal_metrics, study_config["constraints"])

    corner_results: list[dict[str, Any]] = []
    for name, adjustments in study_config.get("corner_cases", {}).items():
        case_config = deepcopy(study_config)
        for parameter, setting in adjustments.items():
            if isinstance(setting, str) and setting in {"low", "high"}:
                spec = study_config["uncertainty"][parameter]
                current_value = case_config["nominal"]
                if parameter == "tank_temperature_k":
                    x0 = float(case_config["nominal"]["performance"]["tank_temperature_k"])
                elif parameter == "fill_fraction":
                    x0 = float(case_config["nominal"]["blowdown"]["tank"]["initial_fill_fraction"])
                elif parameter == "usable_ox_fraction":
                    x0 = float(case_config["nominal"]["blowdown"]["tank"]["usable_oxidizer_fraction"])
                elif parameter == "injector_cd":
                    x0 = float(case_config["nominal"]["blowdown"]["injector"]["cd"])
                elif parameter == "regression_a":
                    x0 = float(case_config["nominal"]["blowdown"]["grain"]["a_reg_si"])
                elif parameter == "regression_n":
                    x0 = float(case_config["nominal"]["blowdown"]["grain"]["n_reg"])
                elif parameter == "cstar_efficiency":
                    x0 = float(case_config["nominal"]["loss_factors"]["cstar_efficiency"])
                elif parameter == "cf_efficiency":
                    x0 = float(case_config["nominal"]["loss_factors"]["cf_efficiency"])
                elif parameter == "usable_fuel_fraction":
                    x0 = float(case_config["nominal"]["blowdown"]["grain"]["fuel_usable_fraction"])
                elif parameter == "injector_dp_fraction":
                    x0 = float(case_config["nominal"]["blowdown"]["injector"]["delta_p_fraction_of_pc"])
                elif parameter == "line_loss_multiplier":
                    x0 = float(case_config["nominal"]["loss_factors"]["line_loss_multiplier"])
                elif parameter == "nozzle_discharge_factor":
                    x0 = float(case_config["nominal"]["loss_factors"]["nozzle_discharge_factor"])
                else:
                    raise ValueError(f"Unsupported corner-case parameter: {parameter}")
                value = _varied_value(x0, spec["mode"], float(spec["value"]), setting)
            else:
                value = float(setting)
            _set_parameter(case_config, parameter, value)

        result = run_0d_case(case_config)
        metrics = extract_case_metrics(result, case_config)
        constraints = evaluate_constraints(metrics, case_config["constraints"])
        corner_results.append(
            {
                "case_name": name,
                "result": result,
                "metrics": metrics,
                "constraints": constraints,
            }
        )

    return {
        "nominal": {
            "result": nominal_result,
            "metrics": nominal_metrics,
            "constraints": nominal_constraints,
        },
        "corners": corner_results,
        "config": study_config,
    }
