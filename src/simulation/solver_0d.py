"""Reusable 0D solver facade built on top of the legacy blowdown model."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

import numpy as np

from blowdown_hybrid.calculations import build_runtime_inputs
from blowdown_hybrid.solver import simulate
from blowdown_hybrid.ui_backend import build_config_from_payload

from src.sizing.first_pass_sizing import throat_area_from_mass_flow, total_mass_flow_from_thrust
from src.simulation.stop_conditions import classify_stop_reason
from src.units import bar_to_pa, pa_to_bar


def build_seed_case(performance: Mapping[str, Any], loss_factors: Mapping[str, Any] | None = None) -> dict[str, float]:
    factors = dict(loss_factors or {})
    cstar_efficiency = float(factors.get("cstar_efficiency", 1.0))
    cf_efficiency = float(factors.get("cf_efficiency", 1.0))
    nozzle_discharge_factor = float(factors.get("nozzle_discharge_factor", 1.0))

    target_thrust_n = float(performance["target_thrust_n"])
    isp_s = float(performance["isp_s"])
    pc_bar = float(performance["pc_bar"])
    ae_at = float(performance["ae_at"])
    cstar_mps = float(performance["cstar_mps"]) * cstar_efficiency
    cf = float(performance["cf"]) * cf_efficiency * nozzle_discharge_factor
    if cstar_mps <= 0.0 or cf <= 0.0:
        raise ValueError("Effective c* and Cf must remain positive after applying loss factors.")

    mdot_total_kg_s = total_mass_flow_from_thrust(target_thrust_n, isp_s)
    throat_area_m2 = throat_area_from_mass_flow(mdot_total_kg_s, cstar_mps, bar_to_pa(pc_bar))
    exit_area_m2 = throat_area_m2 * ae_at

    return {
        "target_thrust_n": target_thrust_n,
        "thrust_sl_n": target_thrust_n,
        "of": float(performance["of_ratio"]),
        "isp_s": isp_s,
        "pc_bar": pc_bar,
        "oxidizer_temp_k": float(performance["tank_temperature_k"]),
        "fuel_temp_k": float(performance["fuel_temperature_k"]),
        "abs_vol_frac": float(performance["abs_volume_fraction"]),
        "cstar_mps": cstar_mps,
        "cf": cf,
        "at_m2": throat_area_m2,
        "ae_m2": exit_area_m2,
        "ae_at": ae_at,
        "mdot_total_kg_s": mdot_total_kg_s,
    }


def _build_blowdown_payload(nominal_case_config: Mapping[str, Any]) -> dict[str, Any]:
    payload = deepcopy(dict(nominal_case_config["blowdown"]))
    performance = nominal_case_config["performance"]
    loss_factors = nominal_case_config.get("loss_factors", {})
    payload.setdefault("tank", {})["initial_temp_k"] = float(performance["tank_temperature_k"])

    line_loss_multiplier = float(loss_factors.get("line_loss_multiplier", 1.0))
    payload.setdefault("feed", {})["friction_factor"] = float(payload["feed"]["friction_factor"]) * line_loss_multiplier
    payload["feed"]["minor_loss_k_total"] = float(payload["feed"]["minor_loss_k_total"]) * line_loss_multiplier
    return payload


def _mass_remaining_history(initial_mass_kg: float, mdot_ox_kg_s: np.ndarray, dt_s: float) -> np.ndarray:
    consumed_before_step = np.concatenate(([0.0], np.cumsum(mdot_ox_kg_s[:-1] * dt_s))) if len(mdot_ox_kg_s) else np.array([])
    return np.maximum(float(initial_mass_kg) - consumed_before_step, 0.0)


def _extend_time_axis(time_s: np.ndarray, dt_s: float) -> np.ndarray:
    if time_s.size == 0:
        return np.array([], dtype=float)
    return np.append(time_s, time_s[-1] + dt_s)


def _standardize_history(runtime: dict[str, Any], raw_history: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    dt_s = float(runtime["simulation"].dt_s)
    time_s = np.asarray(raw_history["time_s"], dtype=float)
    mdot_ox = np.asarray(raw_history["mdot_ox_kg_s"], dtype=float)
    port_radius_m = np.asarray(raw_history["port_radius_m"], dtype=float)
    outer_radius_m = runtime["grain"].outer_radius_m
    grain_web_remaining_m = (
        np.full_like(port_radius_m, np.nan)
        if outer_radius_m is None
        else np.maximum(float(outer_radius_m) - port_radius_m, 0.0)
    )

    return {
        "t": time_s,
        "t_s": time_s,
        "tank_pressure_pa": np.asarray(raw_history["tank_p_pa"], dtype=float),
        "tank_pressure_bar": np.asarray(raw_history["tank_p_pa"], dtype=float) / 1.0e5,
        "tank_temperature_k": np.asarray(raw_history["tank_T_k"], dtype=float),
        "tank_quality": np.asarray(raw_history["tank_quality"], dtype=float),
        "oxidizer_mass_remaining_kg": _mass_remaining_history(runtime["tank"].initial_mass_kg, mdot_ox, dt_s),
        "mdot_ox_kg_s": mdot_ox,
        "mdot_f_kg_s": np.asarray(raw_history["mdot_f_kg_s"], dtype=float),
        "of_ratio": np.asarray(raw_history["of_ratio"], dtype=float),
        "pc_pa": np.asarray(raw_history["pc_pa"], dtype=float),
        "pc_bar": np.asarray(raw_history["pc_pa"], dtype=float) / 1.0e5,
        "thrust_n": np.asarray(raw_history["thrust_n"], dtype=float),
        "port_radius_m": port_radius_m,
        "port_radius_mm": port_radius_m * 1000.0,
        "grain_web_remaining_m": grain_web_remaining_m,
        "grain_web_remaining_mm": grain_web_remaining_m * 1000.0,
        "injector_inlet_pressure_bar": np.asarray(raw_history["p_inj_in_pa"], dtype=float) / 1.0e5,
        "feed_pressure_drop_bar": np.asarray(raw_history["dp_feed_pa"], dtype=float) / 1.0e5,
        "injector_delta_p_bar": np.asarray(raw_history["dp_inj_pa"], dtype=float) / 1.0e5,
        "oxidizer_flux_kg_m2_s": np.asarray(raw_history["Gox_kg_m2_s"], dtype=float),
        "regression_rate_m_s": np.asarray(raw_history["rdot_m_s"], dtype=float),
        "regression_rate_mm_s": np.asarray(raw_history["rdot_m_s"], dtype=float) * 1000.0,
        "isp_s": np.asarray(raw_history["isp_s"], dtype=float),
        "integration_time_s": _extend_time_axis(time_s, dt_s),
    }


def build_nominal_case_config(config: Mapping[str, Any]) -> dict[str, Any]:
    return deepcopy(dict(config.get("nominal", config)))


def run_0d_case(config: Mapping[str, Any], verbose: bool = False) -> dict[str, Any]:
    del verbose
    nominal = build_nominal_case_config(config)
    warnings: list[str] = []

    try:
        seed_case = build_seed_case(nominal["performance"], nominal.get("loss_factors"))
        blowdown_payload = _build_blowdown_payload(nominal)
        runtime = build_runtime_inputs(blowdown_payload, seed_case)
        simulation = simulate(
            tank_cfg=runtime["tank"],
            feed_cfg=runtime["feed"],
            injector_cfg=runtime["injector"],
            grain_cfg=runtime["grain"],
            nozzle_cfg=runtime["nozzle"],
            sim_cfg=runtime["simulation"],
            initial_mdot_ox_guess_kg_s=runtime["derived"]["target_mdot_ox_kg_s"],
            initial_pc_guess_pa=runtime["design_point"].chamber_pressure_pa,
        )
        status, stop_warnings = classify_stop_reason(simulation["stop_reason"])
        warnings.extend(stop_warnings)
        history = _standardize_history(runtime, simulation["history"])
        return {
            "status": status,
            "stop_reason": simulation["stop_reason"],
            "warnings": warnings,
            "history": history,
            "raw_history": simulation["history"],
            "seed_case": seed_case,
            "runtime": {
                **runtime,
                "history": simulation["history"],
                "step_count": simulation["step_count"],
                "target_step_count": simulation["target_step_count"],
                "stop_reason": simulation["stop_reason"],
            },
            "resolved_config": nominal,
        }
    except Exception as exc:
        warnings.append(str(exc))
        return {
            "status": "failed",
            "stop_reason": "solver_failure",
            "warnings": warnings,
            "history": {},
            "raw_history": {},
            "seed_case": None,
            "runtime": None,
            "resolved_config": nominal,
        }
