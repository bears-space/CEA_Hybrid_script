"""Reusable 0D solver facade built on top of the legacy blowdown model."""

from __future__ import annotations

from copy import deepcopy
import traceback
from typing import Any, Mapping

import numpy as np

from src.cea_hybrid.defaults import get_default_raw_config
from src.blowdown_hybrid.calculations import build_runtime_inputs
from src.blowdown_hybrid.solver import simulate
from src.blowdown_hybrid.ui_backend import build_config_from_payload

from src.models.nozzle import STANDARD_SEA_LEVEL_PRESSURE_PA, evaluate_nozzle_performance
from src.sizing.first_pass_sizing import throat_area_from_mass_flow, total_mass_flow_from_thrust
from src.simulation.stop_conditions import classify_stop_reason
from src.sizing.geometry_types import GeometryDefinition
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
    nozzle = evaluate_nozzle_performance(
        cstar_mps=cstar_mps,
        cf_vac=cf + (STANDARD_SEA_LEVEL_PRESSURE_PA / bar_to_pa(pc_bar)) * ae_at,
        chamber_pressure_pa=bar_to_pa(pc_bar),
        throat_area_m2=throat_area_m2,
        mdot_total_kg_s=mdot_total_kg_s,
        ambient_pressure_pa=STANDARD_SEA_LEVEL_PRESSURE_PA,
        exit_area_m2=exit_area_m2,
    )

    return {
        "target_thrust_n": target_thrust_n,
        "thrust_ideal_vac_n": nozzle.thrust_vac_n,
        "thrust_vac_n": nozzle.thrust_vac_n,
        "thrust_sea_level_n": nozzle.thrust_actual_n,
        "thrust_sl_n": nozzle.thrust_actual_n,
        "of": float(performance["of_ratio"]),
        "isp_s": isp_s,
        "isp_sl_s": nozzle.isp_actual_s,
        "isp_vac_s": nozzle.isp_vac_s,
        "pc_bar": pc_bar,
        "oxidizer_temp_k": float(performance["tank_temperature_k"]),
        "fuel_temp_k": float(performance["fuel_temperature_k"]),
        "abs_vol_frac": float(performance["abs_volume_fraction"]),
        "cstar_mps": cstar_mps,
        "cf": cf,
        "cf_actual": nozzle.cf_actual,
        "cf_sea_level": nozzle.cf_actual,
        "cf_vac": nozzle.cf_vac,
        "pe_bar": 0.0,
        "at_m2": throat_area_m2,
        "ae_m2": exit_area_m2,
        "ae_at": ae_at,
        "mdot_total_kg_s": mdot_total_kg_s,
    }


def _build_blowdown_payload(nominal_case_config: Mapping[str, Any]) -> dict[str, Any]:
    payload = deepcopy(dict(nominal_case_config["blowdown"]))
    performance = nominal_case_config["performance"]
    loss_factors = nominal_case_config.get("loss_factors", {})
    payload["geometry_policy"] = deepcopy(dict(nominal_case_config.get("geometry_policy", {})))
    payload.setdefault("tank", {})["initial_temp_k"] = float(performance["tank_temperature_k"])

    line_loss_multiplier = float(loss_factors.get("line_loss_multiplier", 1.0))
    payload.setdefault("feed", {})["pressure_drop_multiplier"] = (
        float(payload["feed"].get("pressure_drop_multiplier", 1.0)) * line_loss_multiplier
    )
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
        "tank_mass_kg": np.asarray(raw_history["tank_mass_kg"], dtype=float),
        "oxidizer_mass_remaining_kg": _mass_remaining_history(runtime["tank"].initial_mass_kg, mdot_ox, dt_s),
        "oxidizer_reserve_mass_kg": np.full_like(mdot_ox, float(runtime["tank"].reserve_mass_kg)),
        "mdot_ox_kg_s": mdot_ox,
        "mdot_f_kg_s": np.asarray(raw_history["mdot_f_kg_s"], dtype=float),
        "mdot_total_kg_s": np.asarray(raw_history["mdot_total_kg_s"], dtype=float),
        "of_ratio": np.asarray(raw_history["of_ratio"], dtype=float),
        "pc_pa": np.asarray(raw_history["pc_pa"], dtype=float),
        "pc_bar": np.asarray(raw_history["pc_pa"], dtype=float) / 1.0e5,
        "thrust_transient_actual_n": np.asarray(raw_history["thrust_actual_n"], dtype=float),
        "thrust_vac_n": np.asarray(raw_history["thrust_vac_n"], dtype=float),
        "thrust_n": np.asarray(raw_history["thrust_actual_n"], dtype=float),
        "port_radius_m": port_radius_m,
        "port_radius_mm": port_radius_m * 1000.0,
        "grain_web_remaining_m": grain_web_remaining_m,
        "grain_web_remaining_mm": grain_web_remaining_m * 1000.0,
        "oxidizer_liquid_density_kg_m3": np.asarray(raw_history["rho_liq_kg_m3"], dtype=float),
        "injector_inlet_pressure_pa": np.asarray(raw_history["p_inj_in_pa"], dtype=float),
        "injector_inlet_pressure_bar": np.asarray(raw_history["p_inj_in_pa"], dtype=float) / 1.0e5,
        "feed_pressure_drop_pa": np.asarray(raw_history["dp_feed_pa"], dtype=float),
        "feed_pressure_drop_bar": np.asarray(raw_history["dp_feed_pa"], dtype=float) / 1.0e5,
        "injector_delta_p_pa": np.asarray(raw_history["dp_inj_pa"], dtype=float),
        "injector_delta_p_bar": np.asarray(raw_history["dp_inj_pa"], dtype=float) / 1.0e5,
        "dp_feed_over_pc": np.asarray(raw_history["dp_feed_over_pc"], dtype=float),
        "dp_injector_over_pc": np.asarray(raw_history["dp_inj_over_pc"], dtype=float),
        "dp_total_over_ptank": np.asarray(raw_history["dp_total_over_ptank"], dtype=float),
        "injector_to_feed_dp_ratio": np.asarray(raw_history["injector_to_feed_dp_ratio"], dtype=float),
        "oxidizer_flux_kg_m2_s": np.asarray(raw_history["Gox_kg_m2_s"], dtype=float),
        "regression_rate_m_s": np.asarray(raw_history["rdot_m_s"], dtype=float),
        "regression_rate_mm_s": np.asarray(raw_history["rdot_m_s"], dtype=float) * 1000.0,
        "cstar_effective_mps": np.asarray(raw_history["cstar_mps"], dtype=float),
        "cf_actual": np.asarray(raw_history["cf_actual"], dtype=float),
        "cf_vac": np.asarray(raw_history["cf_vac"], dtype=float),
        "isp_transient_s": np.asarray(raw_history["isp_actual_s"], dtype=float),
        "isp_vac_s": np.asarray(raw_history["isp_vac_s"], dtype=float),
        "isp_s": np.asarray(raw_history["isp_actual_s"], dtype=float),
        "exit_pressure_bar": np.asarray(raw_history["exit_pressure_pa"], dtype=float) / 1.0e5,
        "gamma_e": np.asarray(raw_history["gamma_e"], dtype=float),
        "molecular_weight_exit": np.asarray(raw_history["molecular_weight_exit"], dtype=float),
        "integration_time_s": _extend_time_axis(time_s, dt_s),
    }


def build_nominal_case_config(config: Mapping[str, Any]) -> dict[str, Any]:
    return deepcopy(dict(config.get("nominal", config)))


def prepare_runtime_case(
    config: Mapping[str, Any],
    raw_cea_config: Mapping[str, Any] | None = None,
    *,
    frozen_geometry: GeometryDefinition | None = None,
    injector_geometry: Mapping[str, Any] | None = None,
    injector_source_override: str | None = None,
) -> dict[str, Any]:
    nominal = build_nominal_case_config(config)
    seed_case = build_seed_case(nominal["performance"], nominal.get("loss_factors"))
    blowdown_payload = _build_blowdown_payload(nominal)
    lookup_config = nominal.get("performance_lookup", {})
    runtime = build_runtime_inputs(
        blowdown_payload,
        seed_case,
        include_performance_lookup=bool(lookup_config.get("enabled", True)),
        lookup_config=lookup_config,
        raw_cea_config=raw_cea_config or get_default_raw_config(),
    )
    study_injector_config = dict(config.get("injector_design", config.get("injector_geometry", {})))
    hydraulic_config = dict(config.get("hydraulic_validation", {}))
    hydraulic_source = str(hydraulic_config.get("hydraulic_source", "nominal_uncalibrated"))
    injector_source = (
        str(injector_source_override)
        if injector_source_override is not None
        else (
            "geometry_backcalculated"
            if hydraulic_source == "geometry_plus_coldflow"
            else str(study_injector_config.get("solver_injector_source", "equivalent_manual"))
        )
    )
    if injector_source == "geometry_backcalculated":
        from src.injector_design import apply_injector_geometry_to_runtime, resolve_injector_geometry_for_runtime

        resolved_injector_geometry = resolve_injector_geometry_for_runtime(
            config,
            frozen_geometry=frozen_geometry,
            injector_geometry=injector_geometry,
            raw_cea_config=raw_cea_config,
        )
        runtime = apply_injector_geometry_to_runtime(
            runtime,
            resolved_injector_geometry,
            discharge_model=study_injector_config,
        )
    else:
        runtime = {
            **runtime,
            "derived": {
                **dict(runtime.get("derived", {})),
                "injector_source": "equivalent_manual",
                "injector_geometry_valid": None,
                "injector_geometry_warnings": [],
            },
        }
    if hydraulic_source != "nominal_uncalibrated":
        from src.hydraulic_validation import apply_calibration_package_to_runtime

        runtime = apply_calibration_package_to_runtime(runtime, config)
    return {
        "nominal": nominal,
        "seed_case": seed_case,
        "blowdown_payload": blowdown_payload,
        "runtime": runtime,
    }


def run_0d_case(
    config: Mapping[str, Any],
    verbose: bool = False,
    *,
    frozen_geometry: GeometryDefinition | None = None,
    injector_geometry: Mapping[str, Any] | None = None,
    injector_source_override: str | None = None,
    raw_cea_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    del verbose
    warnings: list[str] = []
    nominal = build_nominal_case_config(config)

    try:
        prepared = prepare_runtime_case(
            config,
            raw_cea_config=raw_cea_config,
            frozen_geometry=frozen_geometry,
            injector_geometry=injector_geometry,
            injector_source_override=injector_source_override,
        )
        nominal = prepared["nominal"]
        seed_case = prepared["seed_case"]
        runtime = prepared["runtime"]
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
        if runtime["derived"].get("performance_lookup_warning"):
            warnings.append(f"Dynamic performance lookup fallback: {runtime['derived']['performance_lookup_warning']}")
        if not runtime["derived"].get("geometry_valid", True):
            warnings.extend(runtime["derived"].get("geometry_warnings", []))
        warnings.extend(runtime["derived"].get("injector_geometry_warnings", []))
        history = _standardize_history(runtime, simulation["history"])
        return {
            "status": status,
            "stop_reason": simulation["stop_reason"],
            "warnings": warnings,
            "traceback": None,
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
        error_traceback = traceback.format_exc()
        return {
            "status": "failed",
            "stop_reason": "solver_failure",
            "warnings": warnings,
            "traceback": error_traceback,
            "history": {},
            "raw_history": {},
            "seed_case": None,
            "runtime": None,
            "resolved_config": nominal,
        }

