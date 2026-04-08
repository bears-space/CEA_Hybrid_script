"""Coupled blowdown solver and time-marching driver."""

import math

import numpy as np

from blowdown_hybrid.constants import G0_MPS2
from blowdown_hybrid.grain import fuel_mass_flow_kg_s
from blowdown_hybrid.hydraulics import feed_pressure_drop_pa, injector_mdot_kg_s
from blowdown_hybrid.models import (
    FeedConfig,
    GrainConfig,
    InjectorConfig,
    NozzleConfig,
    SimulationConfig,
    State,
    TankConfig,
)
from blowdown_hybrid.thermo import initial_tank_state_from_mass_and_temperature, tank_state_from_mass_energy_volume


class BlowdownCancelled(Exception):
    pass


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
    )

    mdot_guess = max(mdot_ox_guess_kg_s, 1e-6)
    pc_guess = max(pc_guess_pa, 1e3)

    for _ in range(sim_cfg.max_inner_iterations):
        dp_feed = feed_pressure_drop_pa(mdot_guess, tank.rho_l_kg_m3, feed_cfg)
        p_inj_in = tank.p_pa - dp_feed
        dp_inj = p_inj_in - pc_guess

        mdot_ox_raw = injector_mdot_kg_s(
            cd=injector_cfg.cd,
            total_area_m2=injector_cfg.total_area_m2,
            rho_kg_m3=tank.rho_l_kg_m3,
            delta_p_pa=dp_inj,
        )

        gox, rdot, mdot_f = fuel_mass_flow_kg_s(mdot_ox_raw, grain_cfg, state.port_radius_m)
        mdot_total = mdot_ox_raw + mdot_f
        pc_raw = mdot_total * nozzle_cfg.cstar_mps / nozzle_cfg.throat_area_m2

        mdot_new = (1.0 - sim_cfg.relaxation) * mdot_guess + sim_cfg.relaxation * mdot_ox_raw
        pc_new = (1.0 - sim_cfg.relaxation) * pc_guess + sim_cfg.relaxation * pc_raw

        mdot_err = abs(mdot_new - mdot_guess) / max(abs(mdot_guess), 1e-9)
        pc_err = abs(pc_new - pc_guess) / max(abs(pc_guess), 1e-9)

        mdot_guess = mdot_new
        pc_guess = pc_new

        if mdot_err < sim_cfg.relative_tolerance and pc_err < sim_cfg.relative_tolerance:
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
    gox, rdot, mdot_f = fuel_mass_flow_kg_s(mdot_ox, grain_cfg, state.port_radius_m)
    mdot_total = mdot_ox + mdot_f
    pc_pa = mdot_total * nozzle_cfg.cstar_mps / nozzle_cfg.throat_area_m2
    thrust_n = nozzle_cfg.cf * pc_pa * nozzle_cfg.throat_area_m2
    of_ratio = mdot_ox / mdot_f if mdot_f > 0.0 else np.inf
    isp_s = thrust_n / (mdot_total * G0_MPS2) if mdot_total > 0.0 else 0.0

    return {
        "time_s": state.time_s,
        "tank_T_k": tank.T_k,
        "tank_p_pa": tank.p_pa,
        "tank_quality": tank.quality,
        "rho_liq_kg_m3": tank.rho_l_kg_m3,
        "h_liq_j_kg": tank.h_l_j_kg,
        "dp_feed_pa": dp_feed,
        "dp_inj_pa": dp_inj,
        "p_inj_in_pa": p_inj_in,
        "pc_pa": pc_pa,
        "mdot_ox_kg_s": mdot_ox,
        "mdot_f_kg_s": mdot_f,
        "mdot_total_kg_s": mdot_total,
        "of_ratio": of_ratio,
        "Gox_kg_m2_s": gox,
        "rdot_m_s": rdot,
        "port_radius_m": state.port_radius_m,
        "thrust_n": thrust_n,
        "isp_s": isp_s,
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
        if grain_cfg.outer_radius_m is not None and state.port_radius_m >= grain_cfg.outer_radius_m:
            stop_reason = "port_radius_reached_outer_radius"
            break

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
        history.append(step)

        if progress_callback is not None:
            progress_callback(step_index + 1, target_step_count)

        if step["tank_quality"] >= sim_cfg.stop_when_tank_quality_exceeds:
            stop_reason = "tank_quality_limit_exceeded"
            break

        dt_s = sim_cfg.dt_s
        state = State(
            time_s=state.time_s + dt_s,
            tank_mass_kg=max(state.tank_mass_kg - step["mdot_ox_kg_s"] * dt_s, 0.0),
            tank_internal_energy_j=state.tank_internal_energy_j - step["mdot_ox_kg_s"] * step["h_liq_j_kg"] * dt_s,
            port_radius_m=state.port_radius_m + step["rdot_m_s"] * dt_s,
        )
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
