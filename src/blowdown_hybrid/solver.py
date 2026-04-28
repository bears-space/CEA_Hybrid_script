"""Coupled blowdown solver and time-marching driver."""

import math

import numpy as np

from .constants import G0_MPS2
from .grain import fuel_mass_flow_kg_s
from .hydraulics import feed_pressure_drop_pa, injector_mdot_kg_s
from .models import (
    FeedConfig,
    GrainConfig,
    InjectorConfig,
    NozzleConfig,
    SimulationConfig,
    State,
    TankConfig,
)
from .thermo import (
    TankStateLimitReached,
    initial_tank_state_from_mass_and_temperature,
    tank_state_from_mass_energy_volume,
)
from src.analysis.pressure_budget import pressure_budget
from src.models.nozzle import cf_vac_from_isp_and_cstar, evaluate_nozzle_performance


class BlowdownCancelled(Exception):
    pass


_QUALITY_LIMIT_PREFLIGHT_MARGIN = 0.07
_FLOW_SOLVER_ABS_TOL_KG_S = 1e-8


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

    cf_vac = float(nozzle_cfg.cf_vac if nozzle_cfg.cf_vac is not None else cf_vac_from_isp_and_cstar(
        nozzle_cfg.cf * nozzle_cfg.cstar_mps / G0_MPS2,
        nozzle_cfg.cstar_mps,
    ))
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


def _step_candidate(
    tank,
    state: State,
    feed_cfg: FeedConfig,
    injector_cfg: InjectorConfig,
    grain_cfg: GrainConfig,
    nozzle_cfg: NozzleConfig,
    sim_cfg: SimulationConfig,
    *,
    mdot_ox_kg_s: float,
    chamber_pressure_reference_pa: float,
) -> dict[str, float]:
    mdot_ox = max(float(mdot_ox_kg_s), 0.0)
    dp_feed = feed_pressure_drop_pa(mdot_ox, tank.rho_l_kg_m3, feed_cfg)
    p_inj_in = tank.p_pa - dp_feed
    gox, rdot, mdot_f = fuel_mass_flow_kg_s(mdot_ox, grain_cfg, state.port_radius_m)
    mdot_total = mdot_ox + mdot_f
    of_ratio = mdot_ox / mdot_f if mdot_f > 0.0 else np.inf

    # The transient lookup varies c* with O/F; use a bounded pressure probe for that lookup,
    # then close chamber pressure from mdot * c* / At.
    probe_pressure_pa = max(min(float(chamber_pressure_reference_pa), max(p_inj_in, 1e3)), 1e3)
    performance_probe = _evaluate_performance(
        nozzle_cfg,
        of_ratio=of_ratio,
        chamber_pressure_pa=probe_pressure_pa,
        mdot_total_kg_s=mdot_total,
        ambient_pressure_pa=sim_cfg.ambient_pressure_pa,
    )
    pc_pa = mdot_total * performance_probe["cstar_mps"] / nozzle_cfg.throat_area_m2
    dp_inj = p_inj_in - pc_pa
    supported_mdot_ox = injector_mdot_kg_s(
        cd=injector_cfg.cd,
        total_area_m2=injector_cfg.total_area_m2,
        rho_kg_m3=tank.rho_l_kg_m3,
        delta_p_pa=dp_inj,
    )
    return {
        "dp_feed_pa": dp_feed,
        "p_inj_in_pa": p_inj_in,
        "dp_inj_pa": dp_inj,
        "supported_mdot_ox_kg_s": supported_mdot_ox,
        "residual_kg_s": supported_mdot_ox - mdot_ox,
        "mdot_ox_kg_s": mdot_ox,
        "mdot_f_kg_s": mdot_f,
        "mdot_total_kg_s": mdot_total,
        "of_ratio": of_ratio,
        "Gox_kg_m2_s": gox,
        "rdot_m_s": rdot,
        "pc_pa": pc_pa,
    }


def _solve_step_flow(
    tank,
    state: State,
    feed_cfg: FeedConfig,
    injector_cfg: InjectorConfig,
    grain_cfg: GrainConfig,
    nozzle_cfg: NozzleConfig,
    sim_cfg: SimulationConfig,
    *,
    chamber_pressure_reference_pa: float,
) -> dict[str, float]:
    lower = _step_candidate(
        tank,
        state,
        feed_cfg,
        injector_cfg,
        grain_cfg,
        nozzle_cfg,
        sim_cfg,
        mdot_ox_kg_s=0.0,
        chamber_pressure_reference_pa=chamber_pressure_reference_pa,
    )
    max_supported_mdot = injector_mdot_kg_s(
        cd=injector_cfg.cd,
        total_area_m2=injector_cfg.total_area_m2,
        rho_kg_m3=tank.rho_l_kg_m3,
        delta_p_pa=tank.p_pa,
    )
    upper = _step_candidate(
        tank,
        state,
        feed_cfg,
        injector_cfg,
        grain_cfg,
        nozzle_cfg,
        sim_cfg,
        mdot_ox_kg_s=max_supported_mdot,
        chamber_pressure_reference_pa=chamber_pressure_reference_pa,
    )

    if lower["residual_kg_s"] <= _FLOW_SOLVER_ABS_TOL_KG_S:
        return lower
    if upper["residual_kg_s"] > 0.0:
        raise RuntimeError("Unable to bracket a physical injector-flow solution for the current tank state.")

    best = lower if abs(lower["residual_kg_s"]) <= abs(upper["residual_kg_s"]) else upper
    for _ in range(sim_cfg.max_inner_iterations):
        midpoint = 0.5 * (lower["mdot_ox_kg_s"] + upper["mdot_ox_kg_s"])
        candidate = _step_candidate(
            tank,
            state,
            feed_cfg,
            injector_cfg,
            grain_cfg,
            nozzle_cfg,
            sim_cfg,
            mdot_ox_kg_s=midpoint,
            chamber_pressure_reference_pa=chamber_pressure_reference_pa,
        )
        if abs(candidate["residual_kg_s"]) <= abs(best["residual_kg_s"]):
            best = candidate

        flow_tolerance = max(
            sim_cfg.relative_tolerance * max(candidate["mdot_ox_kg_s"], 1.0),
            _FLOW_SOLVER_ABS_TOL_KG_S,
        )
        bracket_width = upper["mdot_ox_kg_s"] - lower["mdot_ox_kg_s"]
        if abs(candidate["residual_kg_s"]) <= flow_tolerance or bracket_width <= flow_tolerance:
            return best

        if candidate["residual_kg_s"] > 0.0:
            lower = candidate
        else:
            upper = candidate

    return best


def solve_coupled_step(
    state: State,
    tank_cfg: TankConfig,
    feed_cfg: FeedConfig,
    injector_cfg: InjectorConfig,
    grain_cfg: GrainConfig,
    nozzle_cfg: NozzleConfig,
    sim_cfg: SimulationConfig,
    mdot_ox_guess_kg_s: float,
    pc_guess_pa: float,
) -> dict:
    """
    Solve the inner coupled algebraic problem for a single time step.
    """
    tank = tank_state_from_mass_energy_volume(
        mass_kg=state.tank_mass_kg,
        total_internal_energy_j=state.tank_internal_energy_j,
        volume_m3=tank_cfg.volume_m3,
        temperature_hint_k=state.tank_temperature_hint_k,
    )

    flow_solution = _solve_step_flow(
        tank,
        state,
        feed_cfg,
        injector_cfg,
        grain_cfg,
        nozzle_cfg,
        sim_cfg,
        chamber_pressure_reference_pa=max(pc_guess_pa, 1e3),
    )

    mdot_ox = flow_solution["mdot_ox_kg_s"]
    mdot_f = flow_solution["mdot_f_kg_s"]
    mdot_total = flow_solution["mdot_total_kg_s"]
    of_ratio = flow_solution["of_ratio"]
    performance = _evaluate_performance(
        nozzle_cfg,
        of_ratio=of_ratio,
        chamber_pressure_pa=max(flow_solution["pc_pa"], 0.0),
        mdot_total_kg_s=mdot_total,
        ambient_pressure_pa=sim_cfg.ambient_pressure_pa,
    )
    pc_pa = flow_solution["pc_pa"]
    thrust_n = performance["thrust_actual_n"]
    isp_s = performance["isp_actual_s"] if mdot_total > 0.0 else 0.0
    budget = pressure_budget(
        tank_pressure_pa=tank.p_pa,
        feed_pressure_drop_pa=flow_solution["dp_feed_pa"],
        injector_inlet_pressure_pa=flow_solution["p_inj_in_pa"],
        injector_delta_p_pa=flow_solution["dp_inj_pa"],
        chamber_pressure_pa=pc_pa,
    )

    return {
        "time_s": state.time_s,
        "tank_mass_kg": state.tank_mass_kg,
        "tank_T_k": tank.T_k,
        "tank_p_pa": tank.p_pa,
        "tank_quality": tank.quality,
        "rho_liq_kg_m3": tank.rho_l_kg_m3,
        "h_liq_j_kg": tank.h_l_j_kg,
        "dp_feed_pa": flow_solution["dp_feed_pa"],
        "dp_inj_pa": flow_solution["dp_inj_pa"],
        "p_inj_in_pa": flow_solution["p_inj_in_pa"],
        "pc_pa": pc_pa,
        "dp_feed_over_pc": budget["dp_feed_over_pc"],
        "dp_inj_over_pc": budget["dp_injector_over_pc"],
        "dp_total_over_ptank": budget["dp_total_over_ptank"],
        "injector_to_feed_dp_ratio": budget["injector_to_feed_dp_ratio"],
        "mdot_ox_kg_s": mdot_ox,
        "mdot_f_kg_s": mdot_f,
        "mdot_total_kg_s": mdot_total,
        "of_ratio": of_ratio,
        "Gox_kg_m2_s": flow_solution["Gox_kg_m2_s"],
        "rdot_m_s": flow_solution["rdot_m_s"],
        "port_radius_m": state.port_radius_m,
        "cstar_mps": performance["cstar_mps"],
        "cf_vac": performance["cf_vac"],
        "cf_actual": performance["cf_actual"],
        "thrust_vac_n": performance["thrust_vac_n"],
        "thrust_actual_n": thrust_n,
        "thrust_n": thrust_n,
        "isp_vac_s": performance["isp_vac_s"],
        "isp_actual_s": isp_s,
        "isp_s": isp_s,
        "exit_pressure_pa": performance["exit_pressure_pa"],
        "gamma_e": performance["gamma_e"],
        "molecular_weight_exit": performance["molecular_weight_exit"],
    }


def simulate(
    tank_cfg: TankConfig,
    feed_cfg: FeedConfig,
    injector_cfg: InjectorConfig,
    grain_cfg: GrainConfig,
    nozzle_cfg: NozzleConfig,
    sim_cfg: SimulationConfig,
    initial_mdot_ox_guess_kg_s: float,
    initial_pc_guess_pa: float,
    progress_callback=None,
    cancel_event=None,
) -> dict:
    """
    Time-march the hybrid system and return history arrays plus stop metadata.
    """
    _, initial_internal_energy_j = initial_tank_state_from_mass_and_temperature(tank_cfg)
    state = State(
        time_s=0.0,
        tank_mass_kg=tank_cfg.initial_mass_kg,
        tank_internal_energy_j=initial_internal_energy_j,
        port_radius_m=grain_cfg.initial_port_radius_m,
        tank_temperature_hint_k=tank_cfg.initial_temp_k,
    )
    history = []
    mdot_guess = initial_mdot_ox_guess_kg_s
    pc_guess = initial_pc_guess_pa
    target_step_count = int(math.ceil(sim_cfg.burn_time_s / sim_cfg.dt_s))
    stop_reason = "burn_time_reached"

    if progress_callback is not None:
        progress_callback(0, target_step_count)

    for step_index in range(target_step_count):
        if cancel_event is not None and cancel_event.is_set():
            raise BlowdownCancelled("Blowdown simulation cancelled.")
        if state.tank_mass_kg <= 0.0:
            stop_reason = "tank_depleted"
            break
        if sim_cfg.oxidizer_depletion_policy == "usable_reserve_or_quality" and state.tank_mass_kg <= tank_cfg.reserve_mass_kg:
            stop_reason = "usable_oxidizer_reserve_reached"
            break
        if grain_cfg.outer_radius_m is not None and state.port_radius_m >= grain_cfg.outer_radius_m:
            stop_reason = "port_radius_reached_outer_radius"
            break

        try:
            step = solve_coupled_step(
                state=state,
                tank_cfg=tank_cfg,
                feed_cfg=feed_cfg,
                injector_cfg=injector_cfg,
                grain_cfg=grain_cfg,
                nozzle_cfg=nozzle_cfg,
                sim_cfg=sim_cfg,
                mdot_ox_guess_kg_s=mdot_guess,
                pc_guess_pa=pc_guess,
            )
        except TankStateLimitReached as exc:
            if not history:
                raise RuntimeError(str(exc)) from exc
            stop_reason = "tank_left_two_phase_region"
            break
        history.append(step)

        if progress_callback is not None:
            progress_callback(step_index + 1, target_step_count)

        if sim_cfg.stop_on_quality_limit and step["tank_quality"] >= sim_cfg.stop_when_tank_quality_exceeds:
            stop_reason = "tank_quality_limit_exceeded"
            break

        dt_s = sim_cfg.dt_s
        next_state = State(
            time_s=state.time_s + dt_s,
            tank_mass_kg=max(state.tank_mass_kg - step["mdot_ox_kg_s"] * dt_s, 0.0),
            tank_internal_energy_j=state.tank_internal_energy_j - step["mdot_ox_kg_s"] * step["h_liq_j_kg"] * dt_s,
            port_radius_m=state.port_radius_m + step["rdot_m_s"] * dt_s,
            tank_temperature_hint_k=step["tank_T_k"],
        )

        # Near the vapor-quality cutoff, preview the next tank state so the solver can terminate
        # cleanly before the following step enters a slow or unsupported thermodynamic region.
        if (
            sim_cfg.stop_on_quality_limit
            and next_state.tank_mass_kg > 0.0
            and step["tank_quality"] >= (
            sim_cfg.stop_when_tank_quality_exceeds - _QUALITY_LIMIT_PREFLIGHT_MARGIN
            )
        ):
            try:
                next_tank = tank_state_from_mass_energy_volume(
                    mass_kg=next_state.tank_mass_kg,
                    total_internal_energy_j=next_state.tank_internal_energy_j,
                    volume_m3=tank_cfg.volume_m3,
                    temperature_hint_k=next_state.tank_temperature_hint_k,
                )
            except TankStateLimitReached:
                stop_reason = "tank_left_two_phase_region"
                break
            if next_tank.quality >= sim_cfg.stop_when_tank_quality_exceeds:
                stop_reason = "tank_quality_limit_exceeded"
                break

        state = next_state
        mdot_guess = max(step["mdot_ox_kg_s"], 1e-6)
        pc_guess = max(step["pc_pa"], 1e3)

    if not history:
        raise RuntimeError("Blowdown simulation produced no time steps.")

    arrays = {}
    for key in history[0]:
        arrays[key] = np.array([row[key] for row in history], dtype=float)

    return {
        "history": arrays,
        "stop_reason": stop_reason,
        "step_count": len(history),
        "target_step_count": target_step_count,
    }

