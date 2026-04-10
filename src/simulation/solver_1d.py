"""Quasi-1D internal ballistics solver built on top of the existing blowdown runtime."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math
from typing import Any, Mapping

import numpy as np

from blowdown_hybrid.constants import G0_MPS2
from blowdown_hybrid.hydraulics import feed_pressure_drop_pa, injector_mdot_kg_s
from blowdown_hybrid.models import FeedConfig, GrainConfig, InjectorConfig, NozzleConfig, TankConfig
from blowdown_hybrid.thermo import initial_tank_state_from_mass_and_temperature, tank_state_from_mass_energy_volume

from src.analysis.pressure_budget import pressure_budget
from src.config_schema import build_design_config
from src.models.nozzle import cf_vac_from_isp_and_cstar, evaluate_nozzle_performance
from src.models.regression import PowerLawRegressionModel
from src.simulation.axial_mesh import AxialMesh, build_axial_mesh
from src.simulation.ballistics_1d import AxialMarchResult, march_port_ballistics
from src.simulation.solver_0d import prepare_runtime_case
from src.simulation.state_1d import Ballistics1DSettings, Ballistics1DState
from src.simulation.stop_conditions import classify_stop_reason
from src.sizing.geometry_types import GeometryDefinition


def _raw_cea_config(cea_data: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if cea_data is None:
        return None
    if "raw_config" in cea_data and isinstance(cea_data["raw_config"], Mapping):
        return cea_data["raw_config"]
    return cea_data


def _evaluate_performance(
    nozzle_cfg: NozzleConfig,
    *,
    of_ratio: float,
    chamber_pressure_pa: float,
    mdot_total_kg_s: float,
    ambient_pressure_pa: float,
) -> dict[str, float]:
    if nozzle_cfg.performance_lookup is not None:
        return nozzle_cfg.performance_lookup.evaluate(
            of_ratio=of_ratio,
            chamber_pressure_pa=chamber_pressure_pa,
            ambient_pressure_pa=ambient_pressure_pa,
            throat_area_m2=nozzle_cfg.throat_area_m2,
            exit_area_m2=nozzle_cfg.exit_area_m2,
            mdot_total_kg_s=mdot_total_kg_s,
        )

    cf_vac = float(
        nozzle_cfg.cf_vac
        if nozzle_cfg.cf_vac is not None
        else cf_vac_from_isp_and_cstar(nozzle_cfg.cf * nozzle_cfg.cstar_mps / G0_MPS2, nozzle_cfg.cstar_mps)
    )
    nozzle = evaluate_nozzle_performance(
        cstar_mps=nozzle_cfg.cstar_mps,
        cf_vac=cf_vac,
        chamber_pressure_pa=chamber_pressure_pa,
        throat_area_m2=nozzle_cfg.throat_area_m2,
        mdot_total_kg_s=mdot_total_kg_s,
        ambient_pressure_pa=ambient_pressure_pa,
        exit_area_m2=nozzle_cfg.exit_area_m2,
        exit_pressure_ratio=nozzle_cfg.exit_pressure_ratio,
        gamma_e=nozzle_cfg.gamma_e,
        molecular_weight_exit=nozzle_cfg.molecular_weight_exit,
    )
    return {
        "cstar_mps": nozzle.cstar_mps,
        "cf_vac": nozzle.cf_vac,
        "cf_actual": nozzle.cf_actual,
        "isp_vac_s": nozzle.isp_vac_s,
        "isp_actual_s": nozzle.isp_actual_s,
        "thrust_vac_n": nozzle.thrust_vac_n,
        "thrust_actual_n": nozzle.thrust_actual_n,
        "exit_pressure_pa": 0.0 if nozzle.exit_pressure_pa is None else nozzle.exit_pressure_pa,
        "gamma_e": 0.0 if nozzle.gamma_e is None else nozzle.gamma_e,
        "molecular_weight_exit": 0.0 if nozzle.molecular_weight_exit is None else nozzle.molecular_weight_exit,
    }


def _settings_from_config(config: Mapping[str, Any]) -> Ballistics1DSettings:
    return Ballistics1DSettings(**dict(config["ballistics_1d"]))


def _station_indices(cell_count: int) -> tuple[int, int, int]:
    mid = max(min(cell_count // 2, cell_count - 1), 0)
    return 0, mid, cell_count - 1


def _geometry_adjusted_runtime(
    runtime: Mapping[str, Any],
    geometry: GeometryDefinition,
    settings: Ballistics1DSettings,
) -> dict[str, Any]:
    grain_cfg: GrainConfig = replace(
        runtime["grain"],
        port_count=int(geometry.port_count),
        initial_port_radius_m=float(geometry.port_radius_initial_m),
        grain_length_m=float(geometry.grain_length_m),
        outer_radius_m=float(geometry.grain_outer_radius_m),
    )
    nozzle_cfg: NozzleConfig = replace(
        runtime["nozzle"],
        throat_area_m2=float(geometry.throat_area_m2),
        exit_area_m2=float(geometry.nozzle_exit_area_m2),
        performance_lookup=(
            runtime["nozzle"].performance_lookup
            if settings.performance_lookup_mode == "cea_table"
            else None
        ),
    )
    simulation = replace(
        runtime["simulation"],
        dt_s=float(settings.time_step_s),
        burn_time_s=float(settings.max_simulation_time_s),
        ambient_pressure_pa=float(settings.ambient_pressure_pa),
        max_inner_iterations=int(settings.max_pressure_iterations),
        relaxation=float(settings.pressure_relaxation),
        relative_tolerance=float(settings.pressure_relative_tolerance),
    )
    return {
        **runtime,
        "grain": grain_cfg,
        "nozzle": nozzle_cfg,
        "simulation": simulation,
    }


def _solve_coupled_1d_step(
    *,
    state: Ballistics1DState,
    tank_cfg: TankConfig,
    feed_cfg: FeedConfig,
    injector_cfg: InjectorConfig,
    grain_cfg: GrainConfig,
    nozzle_cfg: NozzleConfig,
    geometry: GeometryDefinition,
    mesh: AxialMesh,
    settings: Ballistics1DSettings,
    regression_model: PowerLawRegressionModel,
    mdot_ox_guess_kg_s: float,
    pc_guess_pa: float,
) -> tuple[dict[str, float], AxialMarchResult]:
    tank = tank_state_from_mass_energy_volume(
        mass_kg=state.tank_mass_kg,
        total_internal_energy_j=state.tank_internal_energy_j,
        volume_m3=tank_cfg.volume_m3,
    )

    mdot_guess = max(float(mdot_ox_guess_kg_s), 1.0e-6)
    pc_guess = max(float(pc_guess_pa), 1.0e3)

    for _ in range(settings.max_pressure_iterations):
        dp_feed = feed_pressure_drop_pa(mdot_guess, tank.rho_l_kg_m3, feed_cfg)
        p_inj_in = tank.p_pa - dp_feed
        dp_inj = p_inj_in - pc_guess
        mdot_ox_raw = injector_mdot_kg_s(
            cd=injector_cfg.cd,
            total_area_m2=injector_cfg.total_area_m2,
            rho_kg_m3=tank.rho_l_kg_m3,
            delta_p_pa=dp_inj,
        )
        axial = march_port_ballistics(
            mdot_ox_kg_s=mdot_ox_raw,
            port_radii_m=state.port_radii_m,
            geometry=geometry,
            mesh=mesh,
            grain_cfg=grain_cfg,
            regression_model=regression_model,
            axial_correction_mode=settings.axial_correction_mode,
            axial_head_end_bias_strength=settings.axial_head_end_bias_strength,
            axial_bias_decay_fraction=settings.axial_bias_decay_fraction,
        )
        of_ratio = mdot_ox_raw / max(axial.total_fuel_mass_flow_kg_s, 1.0e-12)
        performance = _evaluate_performance(
            nozzle_cfg,
            of_ratio=of_ratio,
            chamber_pressure_pa=pc_guess,
            mdot_total_kg_s=axial.exit_total_mass_flow_kg_s,
            ambient_pressure_pa=settings.ambient_pressure_pa,
        )
        pc_raw = axial.exit_total_mass_flow_kg_s * performance["cstar_mps"] / nozzle_cfg.throat_area_m2

        mdot_new = (1.0 - settings.pressure_relaxation) * mdot_guess + settings.pressure_relaxation * mdot_ox_raw
        pc_new = (1.0 - settings.pressure_relaxation) * pc_guess + settings.pressure_relaxation * pc_raw
        mdot_err = abs(mdot_new - mdot_guess) / max(abs(mdot_guess), 1.0e-9)
        pc_err = abs(pc_new - pc_guess) / max(abs(pc_guess), 1.0e-9)
        mdot_guess = mdot_new
        pc_guess = pc_new
        if mdot_err < settings.pressure_relative_tolerance and pc_err < settings.pressure_relative_tolerance:
            break

    dp_feed = feed_pressure_drop_pa(mdot_guess, tank.rho_l_kg_m3, feed_cfg)
    p_inj_in = tank.p_pa - dp_feed
    dp_inj = p_inj_in - pc_guess
    mdot_ox = injector_mdot_kg_s(
        cd=injector_cfg.cd,
        total_area_m2=injector_cfg.total_area_m2,
        rho_kg_m3=tank.rho_l_kg_m3,
        delta_p_pa=dp_inj,
    )
    axial = march_port_ballistics(
        mdot_ox_kg_s=mdot_ox,
        port_radii_m=state.port_radii_m,
        geometry=geometry,
        mesh=mesh,
        grain_cfg=grain_cfg,
        regression_model=regression_model,
        axial_correction_mode=settings.axial_correction_mode,
        axial_head_end_bias_strength=settings.axial_head_end_bias_strength,
        axial_bias_decay_fraction=settings.axial_bias_decay_fraction,
    )
    of_ratio = mdot_ox / max(axial.total_fuel_mass_flow_kg_s, 1.0e-12)
    performance = _evaluate_performance(
        nozzle_cfg,
        of_ratio=of_ratio,
        chamber_pressure_pa=pc_guess,
        mdot_total_kg_s=axial.exit_total_mass_flow_kg_s,
        ambient_pressure_pa=settings.ambient_pressure_pa,
    )
    chamber_pressure_pa = axial.exit_total_mass_flow_kg_s * performance["cstar_mps"] / nozzle_cfg.throat_area_m2
    performance = _evaluate_performance(
        nozzle_cfg,
        of_ratio=of_ratio,
        chamber_pressure_pa=chamber_pressure_pa,
        mdot_total_kg_s=axial.exit_total_mass_flow_kg_s,
        ambient_pressure_pa=settings.ambient_pressure_pa,
    )
    budget = pressure_budget(
        tank_pressure_pa=tank.p_pa,
        feed_pressure_drop_pa=dp_feed,
        injector_inlet_pressure_pa=p_inj_in,
        injector_delta_p_pa=dp_inj,
        chamber_pressure_pa=chamber_pressure_pa,
    )
    head_index, mid_index, tail_index = _station_indices(mesh.cell_count)
    step = {
        "time_s": state.time_s,
        "tank_mass_kg": state.tank_mass_kg,
        "tank_T_k": tank.T_k,
        "tank_p_pa": tank.p_pa,
        "tank_quality": tank.quality,
        "rho_liq_kg_m3": tank.rho_l_kg_m3,
        "h_liq_j_kg": tank.h_l_j_kg,
        "dp_feed_pa": dp_feed,
        "dp_inj_pa": dp_inj,
        "p_inj_in_pa": p_inj_in,
        "pc_pa": chamber_pressure_pa,
        "dp_feed_over_pc": budget["dp_feed_over_pc"],
        "dp_inj_over_pc": budget["dp_injector_over_pc"],
        "dp_total_over_ptank": budget["dp_total_over_ptank"],
        "injector_to_feed_dp_ratio": budget["injector_to_feed_dp_ratio"],
        "mdot_ox_kg_s": mdot_ox,
        "mdot_f_kg_s": axial.total_fuel_mass_flow_kg_s,
        "mdot_total_kg_s": axial.exit_total_mass_flow_kg_s,
        "of_ratio": of_ratio,
        "cstar_mps": performance["cstar_mps"],
        "cf_vac": performance["cf_vac"],
        "cf_actual": performance["cf_actual"],
        "thrust_vac_n": performance["thrust_vac_n"],
        "thrust_actual_n": performance["thrust_actual_n"],
        "thrust_n": performance["thrust_actual_n"],
        "isp_vac_s": performance["isp_vac_s"],
        "isp_actual_s": performance["isp_actual_s"],
        "isp_s": performance["isp_actual_s"],
        "exit_pressure_pa": performance["exit_pressure_pa"],
        "gamma_e": performance["gamma_e"],
        "molecular_weight_exit": performance["molecular_weight_exit"],
        "free_volume_m3": axial.free_volume_m3,
        "lstar_m": axial.lstar_m,
        "port_radius_head_m": float(state.port_radii_m[head_index]),
        "port_radius_mid_m": float(state.port_radii_m[mid_index]),
        "port_radius_tail_m": float(state.port_radii_m[tail_index]),
        "gox_head_kg_m2_s": float(axial.oxidizer_flux_kg_m2_s[head_index]),
        "gox_mid_kg_m2_s": float(axial.oxidizer_flux_kg_m2_s[mid_index]),
        "gox_tail_kg_m2_s": float(axial.oxidizer_flux_kg_m2_s[tail_index]),
        "rdot_head_m_s": float(axial.regression_rate_m_s[head_index]),
        "rdot_mid_m_s": float(axial.regression_rate_m_s[mid_index]),
        "rdot_tail_m_s": float(axial.regression_rate_m_s[tail_index]),
    }
    return step, axial


def _materialize_scalar_history(history: list[dict[str, float]]) -> dict[str, np.ndarray]:
    arrays: dict[str, np.ndarray] = {}
    for key in history[0]:
        arrays[key] = np.array([row[key] for row in history], dtype=float)
    return arrays


def _snapshot_from_state(state: Ballistics1DState, axial: AxialMarchResult) -> dict[str, Any]:
    return {
        "time_s": state.time_s,
        "port_radius_m": state.port_radii_m.copy(),
        "port_area_m2": axial.port_area_m2.copy(),
        "wetted_perimeter_m": axial.wetted_perimeter_m.copy(),
        "oxidizer_mass_flow_kg_s": axial.oxidizer_mass_flow_kg_s.copy(),
        "oxidizer_flux_kg_m2_s": axial.oxidizer_flux_kg_m2_s.copy(),
        "effective_regression_flux_kg_m2_s": axial.effective_regression_flux_kg_m2_s.copy(),
        "regression_rate_m_s": axial.regression_rate_m_s.copy(),
        "fuel_addition_rate_kg_s": axial.fuel_addition_rate_kg_s.copy(),
        "fuel_addition_rate_kg_s_m": axial.fuel_addition_rate_kg_s_m.copy(),
        "cumulative_fuel_mass_flow_kg_s": axial.cumulative_fuel_mass_flow_kg_s.copy(),
        "total_mass_flow_kg_s": axial.total_mass_flow_kg_s.copy(),
        "local_of_ratio": axial.local_of_ratio.copy(),
    }


def _non_physical_step_message(step: Mapping[str, float], axial: AxialMarchResult) -> str | None:
    scalar_fields = (
        "tank_p_pa",
        "p_inj_in_pa",
        "pc_pa",
        "mdot_ox_kg_s",
        "mdot_f_kg_s",
        "mdot_total_kg_s",
        "of_ratio",
        "cstar_mps",
        "cf_actual",
        "thrust_n",
        "free_volume_m3",
        "lstar_m",
    )
    for field_name in scalar_fields:
        if not math.isfinite(float(step[field_name])):
            return f"Non-finite scalar state detected in 1D solver field '{field_name}'."

    if step["tank_p_pa"] <= 0.0 or step["pc_pa"] < 0.0:
        return "Pressure state became non-physical in the 1D solver."
    if step["mdot_ox_kg_s"] < 0.0 or step["mdot_f_kg_s"] < 0.0 or step["mdot_total_kg_s"] < 0.0:
        return "Mass flow became negative in the 1D solver."
    if step["free_volume_m3"] <= 0.0 or step["lstar_m"] <= 0.0:
        return "Free volume or L* became non-physical in the 1D solver."

    axial_fields = {
        "port_area_m2": axial.port_area_m2,
        "wetted_perimeter_m": axial.wetted_perimeter_m,
        "oxidizer_mass_flow_kg_s": axial.oxidizer_mass_flow_kg_s,
        "oxidizer_flux_kg_m2_s": axial.oxidizer_flux_kg_m2_s,
        "effective_regression_flux_kg_m2_s": axial.effective_regression_flux_kg_m2_s,
        "regression_rate_m_s": axial.regression_rate_m_s,
        "fuel_addition_rate_kg_s": axial.fuel_addition_rate_kg_s,
        "fuel_addition_rate_kg_s_m": axial.fuel_addition_rate_kg_s_m,
        "cumulative_fuel_mass_flow_kg_s": axial.cumulative_fuel_mass_flow_kg_s,
        "total_mass_flow_kg_s": axial.total_mass_flow_kg_s,
        "local_of_ratio": axial.local_of_ratio,
    }
    for field_name, field_value in axial_fields.items():
        values = np.asarray(field_value, dtype=float)
        if not np.all(np.isfinite(values)):
            return f"Non-finite axial state detected in 1D solver field '{field_name}'."

    non_negative_fields = (
        "port_area_m2",
        "wetted_perimeter_m",
        "oxidizer_mass_flow_kg_s",
        "oxidizer_flux_kg_m2_s",
        "effective_regression_flux_kg_m2_s",
        "regression_rate_m_s",
        "fuel_addition_rate_kg_s",
        "fuel_addition_rate_kg_s_m",
        "cumulative_fuel_mass_flow_kg_s",
        "total_mass_flow_kg_s",
        "local_of_ratio",
    )
    for field_name in non_negative_fields:
        if np.any(np.asarray(getattr(axial, field_name), dtype=float) < 0.0):
            return f"Negative axial state detected in 1D solver field '{field_name}'."
    return None


def _standardize_scalar_history(
    runtime: Mapping[str, Any],
    geometry: GeometryDefinition,
    scalar_history: Mapping[str, np.ndarray],
) -> dict[str, np.ndarray]:
    time_s = np.asarray(scalar_history["time_s"], dtype=float)
    dt_s = float(runtime["simulation"].dt_s)
    integration_time_s = np.append(time_s, time_s[-1] + dt_s) if time_s.size else np.array([], dtype=float)
    oxidizer_mass_remaining_kg = runtime["tank"].initial_mass_kg - np.concatenate(
        ([0.0], np.cumsum(np.asarray(scalar_history["mdot_ox_kg_s"][:-1], dtype=float) * dt_s))
    )
    grain_web_head_m = np.maximum(geometry.grain_outer_radius_m - np.asarray(scalar_history["port_radius_head_m"], dtype=float), 0.0)
    grain_web_mid_m = np.maximum(geometry.grain_outer_radius_m - np.asarray(scalar_history["port_radius_mid_m"], dtype=float), 0.0)
    grain_web_tail_m = np.maximum(geometry.grain_outer_radius_m - np.asarray(scalar_history["port_radius_tail_m"], dtype=float), 0.0)

    return {
        "t": time_s,
        "t_s": time_s,
        "integration_time_s": integration_time_s,
        "tank_pressure_pa": np.asarray(scalar_history["tank_p_pa"], dtype=float),
        "tank_pressure_bar": np.asarray(scalar_history["tank_p_pa"], dtype=float) / 1.0e5,
        "tank_temperature_k": np.asarray(scalar_history["tank_T_k"], dtype=float),
        "tank_quality": np.asarray(scalar_history["tank_quality"], dtype=float),
        "tank_mass_kg": np.asarray(scalar_history["tank_mass_kg"], dtype=float),
        "oxidizer_mass_remaining_kg": np.maximum(oxidizer_mass_remaining_kg, 0.0),
        "oxidizer_reserve_mass_kg": np.full_like(time_s, float(runtime["tank"].reserve_mass_kg)),
        "mdot_ox_kg_s": np.asarray(scalar_history["mdot_ox_kg_s"], dtype=float),
        "mdot_f_kg_s": np.asarray(scalar_history["mdot_f_kg_s"], dtype=float),
        "mdot_total_kg_s": np.asarray(scalar_history["mdot_total_kg_s"], dtype=float),
        "of_ratio": np.asarray(scalar_history["of_ratio"], dtype=float),
        "pc_pa": np.asarray(scalar_history["pc_pa"], dtype=float),
        "pc_bar": np.asarray(scalar_history["pc_pa"], dtype=float) / 1.0e5,
        "thrust_transient_actual_n": np.asarray(scalar_history["thrust_actual_n"], dtype=float),
        "thrust_vac_n": np.asarray(scalar_history["thrust_vac_n"], dtype=float),
        "thrust_n": np.asarray(scalar_history["thrust_n"], dtype=float),
        "injector_inlet_pressure_bar": np.asarray(scalar_history["p_inj_in_pa"], dtype=float) / 1.0e5,
        "feed_pressure_drop_bar": np.asarray(scalar_history["dp_feed_pa"], dtype=float) / 1.0e5,
        "injector_delta_p_bar": np.asarray(scalar_history["dp_inj_pa"], dtype=float) / 1.0e5,
        "dp_feed_over_pc": np.asarray(scalar_history["dp_feed_over_pc"], dtype=float),
        "dp_injector_over_pc": np.asarray(scalar_history["dp_inj_over_pc"], dtype=float),
        "dp_total_over_ptank": np.asarray(scalar_history["dp_total_over_ptank"], dtype=float),
        "injector_to_feed_dp_ratio": np.asarray(scalar_history["injector_to_feed_dp_ratio"], dtype=float),
        "cstar_effective_mps": np.asarray(scalar_history["cstar_mps"], dtype=float),
        "cf_actual": np.asarray(scalar_history["cf_actual"], dtype=float),
        "cf_vac": np.asarray(scalar_history["cf_vac"], dtype=float),
        "isp_transient_s": np.asarray(scalar_history["isp_actual_s"], dtype=float),
        "isp_vac_s": np.asarray(scalar_history["isp_vac_s"], dtype=float),
        "isp_s": np.asarray(scalar_history["isp_actual_s"], dtype=float),
        "exit_pressure_bar": np.asarray(scalar_history["exit_pressure_pa"], dtype=float) / 1.0e5,
        "gamma_e": np.asarray(scalar_history["gamma_e"], dtype=float),
        "molecular_weight_exit": np.asarray(scalar_history["molecular_weight_exit"], dtype=float),
        "port_radius_head_mm": np.asarray(scalar_history["port_radius_head_m"], dtype=float) * 1000.0,
        "port_radius_mid_mm": np.asarray(scalar_history["port_radius_mid_m"], dtype=float) * 1000.0,
        "port_radius_tail_mm": np.asarray(scalar_history["port_radius_tail_m"], dtype=float) * 1000.0,
        "port_radius_mm": np.asarray(scalar_history["port_radius_mid_m"], dtype=float) * 1000.0,
        "grain_web_head_mm": grain_web_head_m * 1000.0,
        "grain_web_mid_mm": grain_web_mid_m * 1000.0,
        "grain_web_tail_mm": grain_web_tail_m * 1000.0,
        "grain_web_remaining_mm": grain_web_mid_m * 1000.0,
        "gox_head_kg_m2_s": np.asarray(scalar_history["gox_head_kg_m2_s"], dtype=float),
        "gox_mid_kg_m2_s": np.asarray(scalar_history["gox_mid_kg_m2_s"], dtype=float),
        "gox_tail_kg_m2_s": np.asarray(scalar_history["gox_tail_kg_m2_s"], dtype=float),
        "oxidizer_flux_kg_m2_s": np.asarray(scalar_history["gox_mid_kg_m2_s"], dtype=float),
        "regression_rate_head_mm_s": np.asarray(scalar_history["rdot_head_m_s"], dtype=float) * 1000.0,
        "regression_rate_mid_mm_s": np.asarray(scalar_history["rdot_mid_m_s"], dtype=float) * 1000.0,
        "regression_rate_tail_mm_s": np.asarray(scalar_history["rdot_tail_m_s"], dtype=float) * 1000.0,
        "regression_rate_mm_s": np.asarray(scalar_history["rdot_mid_m_s"], dtype=float) * 1000.0,
        "free_volume_m3": np.asarray(scalar_history["free_volume_m3"], dtype=float),
        "lstar_m": np.asarray(scalar_history["lstar_m"], dtype=float),
    }


def run_1d_ballistics_case(
    config: Mapping[str, Any],
    geometry: GeometryDefinition,
    cea_data: Mapping[str, Any] | None = None,
    optional_seed_state: Mapping[str, Any] | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    del verbose
    study_config = build_design_config(config)
    settings = _settings_from_config(study_config)
    warnings = list(geometry.warnings)
    warnings.append(
        "Quasi-1D axial marching keeps oxidizer mass flow conserved along the port and adds fuel locally; "
        "separate oxidizer-consumption bookkeeping is a future refinement."
    )

    try:
        prepared = prepare_runtime_case(study_config, raw_cea_config=_raw_cea_config(cea_data))
        runtime = _geometry_adjusted_runtime(prepared["runtime"], geometry, settings)
        if not geometry.geometry_valid:
            warnings.append("Frozen geometry is flagged invalid; 1D results should be treated as diagnostic only.")

        mesh = build_axial_mesh(geometry, settings.axial_cell_count)
        regression_model = PowerLawRegressionModel(
            a_reg_si=float(runtime["grain"].a_reg_si),
            n_reg=float(runtime["grain"].n_reg),
        )
        _, initial_internal_energy_j = initial_tank_state_from_mass_and_temperature(runtime["tank"])
        state = Ballistics1DState(
            time_s=0.0,
            tank_mass_kg=float(runtime["tank"].initial_mass_kg),
            tank_internal_energy_j=float(initial_internal_energy_j),
            port_radii_m=np.full(mesh.cell_count, float(geometry.port_radius_initial_m), dtype=float),
        )
        mdot_guess = float(
            optional_seed_state.get("initial_mdot_ox_guess_kg_s", runtime["derived"]["target_mdot_ox_kg_s"])
            if optional_seed_state
            else runtime["derived"]["target_mdot_ox_kg_s"]
        )
        pc_guess = float(
            optional_seed_state.get("initial_pc_guess_pa", runtime["design_point"].chamber_pressure_pa)
            if optional_seed_state
            else runtime["design_point"].chamber_pressure_pa
        )

        scalar_history: list[dict[str, float]] = []
        axial_snapshots: list[dict[str, Any]] = []
        target_step_count = int(math.ceil(settings.max_simulation_time_s / settings.time_step_s))
        stop_reason = "burn_time_reached"

        for step_index in range(target_step_count):
            if state.tank_mass_kg <= 0.0:
                stop_reason = "tank_depleted"
                break
            if runtime["simulation"].oxidizer_depletion_policy == "usable_reserve_or_quality" and state.tank_mass_kg <= runtime["tank"].reserve_mass_kg:
                stop_reason = "usable_oxidizer_reserve_reached"
                break
            if np.any(state.port_radii_m >= geometry.grain_outer_radius_m):
                stop_reason = "grain_burnthrough"
                break

            step, axial = _solve_coupled_1d_step(
                state=state,
                tank_cfg=runtime["tank"],
                feed_cfg=runtime["feed"],
                injector_cfg=runtime["injector"],
                grain_cfg=runtime["grain"],
                nozzle_cfg=runtime["nozzle"],
                geometry=geometry,
                mesh=mesh,
                settings=settings,
                regression_model=regression_model,
                mdot_ox_guess_kg_s=mdot_guess,
                pc_guess_pa=pc_guess,
            )
            if not all(
                np.all(np.isfinite(value))
                for value in (
                    axial.port_area_m2,
                    axial.regression_rate_m_s,
                    axial.total_mass_flow_kg_s,
                    axial.oxidizer_mass_flow_kg_s,
                )
            ):
                stop_reason = "non_finite_state"
                break
            if step["mdot_ox_kg_s"] <= 1.0e-9 or step["mdot_total_kg_s"] <= 1.0e-9:
                stop_reason = "flow_stopped"
                break
            non_physical_message = _non_physical_step_message(step, axial)
            if non_physical_message is not None:
                stop_reason = "non_physical_state"
                warnings.append(non_physical_message)
                break

            scalar_history.append(step)
            if step_index % settings.record_every_n_steps == 0 or step_index == target_step_count - 1:
                axial_snapshots.append(_snapshot_from_state(state, axial))

            if runtime["simulation"].stop_on_quality_limit and step["tank_quality"] >= runtime["simulation"].stop_when_tank_quality_exceeds:
                stop_reason = "tank_quality_limit_exceeded"
                break

            web_remaining_m = np.maximum(geometry.grain_outer_radius_m - state.port_radii_m, 1.0e-9)
            growth_fraction = float(np.max(axial.regression_rate_m_s * settings.time_step_s / web_remaining_m))
            if growth_fraction > settings.max_port_growth_fraction_per_step:
                stop_reason = "port_growth_step_limit_exceeded"
                warnings.append(
                    f"Step-size stability limit exceeded with fractional web growth {growth_fraction:.3f}; reduce ballistics_1d.time_step_s."
                )
                break

            state = Ballistics1DState(
                time_s=state.time_s + settings.time_step_s,
                tank_mass_kg=max(state.tank_mass_kg - step["mdot_ox_kg_s"] * settings.time_step_s, 0.0),
                tank_internal_energy_j=state.tank_internal_energy_j - step["mdot_ox_kg_s"] * step["h_liq_j_kg"] * settings.time_step_s,
                port_radii_m=state.port_radii_m + axial.regression_rate_m_s * settings.time_step_s,
            )
            mdot_guess = max(step["mdot_ox_kg_s"], 1.0e-6)
            pc_guess = max(step["pc_pa"], 1.0e3)

        if not scalar_history:
            raise RuntimeError("1D ballistics simulation produced no converged time steps.")

        if axial_snapshots and state.time_s > float(axial_snapshots[-1]["time_s"]) + 1.0e-12:
            try:
                terminal_axial = march_port_ballistics(
                    mdot_ox_kg_s=mdot_guess,
                    port_radii_m=state.port_radii_m,
                    geometry=geometry,
                    mesh=mesh,
                    regression_model=regression_model,
                    grain_cfg=runtime["grain"],
                    axial_correction_mode=settings.axial_correction_mode,
                    axial_head_end_bias_strength=settings.axial_head_end_bias_strength,
                    axial_bias_decay_fraction=settings.axial_bias_decay_fraction,
                )
                axial_snapshots.append(_snapshot_from_state(state, terminal_axial))
            except Exception as exc:
                warnings.append(f"Terminal axial snapshot unavailable: {exc}")

        scalar_arrays = _materialize_scalar_history(scalar_history)
        standardized_history = _standardize_scalar_history(runtime, geometry, scalar_arrays)
        axial_history = {
            "time_s": np.array([item["time_s"] for item in axial_snapshots], dtype=float),
            "x_m": mesh.cell_centers_m.copy(),
            "cell_length_m": mesh.cell_lengths_m.copy(),
            "port_radius_m": np.stack([item["port_radius_m"] for item in axial_snapshots]),
            "port_radius_mm": np.stack([item["port_radius_m"] for item in axial_snapshots]) * 1000.0,
            "port_area_m2": np.stack([item["port_area_m2"] for item in axial_snapshots]),
            "wetted_perimeter_m": np.stack([item["wetted_perimeter_m"] for item in axial_snapshots]),
            "oxidizer_mass_flow_kg_s": np.stack([item["oxidizer_mass_flow_kg_s"] for item in axial_snapshots]),
            "oxidizer_flux_kg_m2_s": np.stack([item["oxidizer_flux_kg_m2_s"] for item in axial_snapshots]),
            "effective_regression_flux_kg_m2_s": np.stack(
                [item["effective_regression_flux_kg_m2_s"] for item in axial_snapshots]
            ),
            "regression_rate_m_s": np.stack([item["regression_rate_m_s"] for item in axial_snapshots]),
            "regression_rate_mm_s": np.stack([item["regression_rate_m_s"] for item in axial_snapshots]) * 1000.0,
            "fuel_addition_rate_kg_s": np.stack([item["fuel_addition_rate_kg_s"] for item in axial_snapshots]),
            "fuel_addition_rate_kg_s_m": np.stack([item["fuel_addition_rate_kg_s_m"] for item in axial_snapshots]),
            "cumulative_fuel_mass_flow_kg_s": np.stack(
                [item["cumulative_fuel_mass_flow_kg_s"] for item in axial_snapshots]
            ),
            "total_mass_flow_kg_s": np.stack([item["total_mass_flow_kg_s"] for item in axial_snapshots]),
            "local_of_ratio": np.stack([item["local_of_ratio"] for item in axial_snapshots]),
        }
        status, stop_warnings = classify_stop_reason(stop_reason)
        warnings.extend(stop_warnings)
        runtime_payload = deepcopy(runtime)
        runtime_payload["derived"] = {
            **dict(runtime_payload.get("derived", {})),
            "geometry_valid": bool(runtime_payload.get("derived", {}).get("geometry_valid", True) and geometry.geometry_valid),
        }
        runtime_payload["frozen_geometry"] = geometry
        runtime_payload["axial_mesh"] = mesh
        runtime_payload["ballistics_settings"] = settings
        return {
            "status": status,
            "stop_reason": stop_reason,
            "warnings": warnings,
            "history": standardized_history,
            "raw_history": scalar_arrays,
            "axial_history": axial_history,
            "final_state": state,
            "runtime": runtime_payload,
            "seed_case": prepared["seed_case"],
            "resolved_config": study_config,
            "comparison": None,
        }
    except Exception as exc:
        warnings.append(str(exc))
        return {
            "status": "failed",
            "stop_reason": "solver_failure",
            "warnings": warnings,
            "history": {},
            "raw_history": {},
            "axial_history": {},
            "final_state": None,
            "runtime": None,
            "seed_case": None,
            "resolved_config": study_config,
            "comparison": None,
        }
