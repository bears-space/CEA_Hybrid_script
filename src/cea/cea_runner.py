"""Callable CEA runners that preserve the legacy project behavior."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from cea_hybrid.calculations import build_cea_objects, run_case as legacy_run_case
from cea_hybrid.config import build_config as build_legacy_config
from cea_hybrid.defaults import get_default_raw_config
from cea_hybrid.outputs import write_outputs as legacy_write_outputs
from cea_hybrid.sweep import run_sweep as legacy_run_sweep

from src.cea.cea_parser import dict_to_performance_point, dict_to_sweep_result
from src.cea.cea_types import CEAPerformancePoint, CEASweepResult


def _single_case_raw_config(base_raw: Mapping[str, Any] | None, case_input: Mapping[str, Any]) -> dict[str, Any]:
    raw = deepcopy(dict(base_raw or get_default_raw_config()))
    raw["target_thrust_n"] = float(case_input.get("target_thrust_n", raw["target_thrust_n"]))
    raw["max_exit_diameter_cm"] = float(case_input.get("max_exit_diameter_cm", raw["max_exit_diameter_cm"]))
    raw["max_area_ratio"] = float(case_input.get("max_area_ratio", raw.get("max_area_ratio", 24.0)))
    raw["ae_at_cap_mode"] = case_input.get("ae_at_cap_mode", raw.get("ae_at_cap_mode", "exit_diameter"))
    raw["pc_bar"] = float(case_input["pc_bar"])
    raw["sweeps"] = deepcopy(raw["sweeps"])
    raw["sweeps"]["abs_volume_fractions"] = [float(case_input["abs_vol_frac"])]
    raw["sweeps"]["fuel_temperatures_k"] = [float(case_input["fuel_temp_k"])]
    raw["sweeps"]["oxidizer_temperatures_k"] = [float(case_input["oxidizer_temp_k"])]
    raw["sweeps"]["of"] = {"values": [float(case_input["of"])]}
    raw["sweeps"]["ae_at"] = {
        "custom_enabled": True,
        "start": float(case_input["ae_at"]),
        "stop": float(case_input["ae_at"]),
        "step": 1.0,
        "cf_search_upper_bound": float(case_input.get("cf_search_upper_bound", 3.0)),
    }
    return raw


def run_cea_case(cea_config: Mapping[str, Any]) -> CEAPerformancePoint:
    if "case_input" in cea_config:
        raw = _single_case_raw_config(cea_config.get("base_config"), cea_config["case_input"])
    else:
        raw = dict(cea_config)
    config = build_legacy_config(raw)
    _, reactants, solver = build_cea_objects(config)
    row = legacy_run_case(
        config,
        reactants,
        solver,
        float(config["abs_volume_fractions"][0]),
        float(config["fuel_temperatures_k"][0]),
        float(config["oxidizer_temperatures_k"][0]),
        float(config["of_values"][0]),
        float(config["ae_at_values"][0]),
    )
    if row is None:
        raise RuntimeError("CEA single-case run did not converge.")
    return dict_to_performance_point(row)


def run_cea_sweep(cea_config: Mapping[str, Any]) -> CEASweepResult:
    config = build_legacy_config(dict(cea_config))
    payload = legacy_run_sweep(config)
    return dict_to_sweep_result(config, payload)


def write_cea_outputs(output_dir, raw_config: Mapping[str, Any], sweep_result: CEASweepResult):
    payload = {
        "cases": [case.raw for case in sweep_result.cases],
        "failures": sweep_result.failures,
        "total_combinations": sweep_result.total_combinations,
        "cpu_workers": sweep_result.cpu_workers,
        "backend": sweep_result.backend,
        "gpu_enabled": sweep_result.gpu_enabled,
    }
    return legacy_write_outputs(output_dir, build_legacy_config(dict(raw_config)), payload)
