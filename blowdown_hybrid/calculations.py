"""High-level orchestration for the integrated preliminary 0D blowdown model."""

from __future__ import annotations

from blowdown_hybrid.config import (
    build_config,
    injector_pressure_drop_fraction_for_mode,
    regression_parameters_for_mode,
)
from blowdown_hybrid.constants import (
    INJECTOR_DELTA_P_MODE_EXPLICIT,
    UI_MODE_ADVANCED,
)
from blowdown_hybrid.defaults import (
    PROJECT_DEFAULT_FUEL_USABLE_FRACTION,
    PROJECT_DEFAULT_INJECTOR_CD,
    PROJECT_DEFAULT_INJECTOR_HOLE_COUNT,
    PROJECT_DEFAULT_PORT_COUNT,
    PROJECT_DEFAULT_USABLE_OXIDIZER_FRACTION,
)
from blowdown_hybrid.first_pass import (
    blend_density_from_volume_fraction,
    equivalent_injector_hole_diameter,
    fuel_mass_flow,
    grain_length_from_fuel_mass_flow,
    grain_outer_radius_from_loaded_fuel_mass,
    initial_port_radius_from_target_gox,
    initial_total_port_area,
    injector_delta_p_from_fraction_of_pc,
    injector_total_area_from_mass_flow,
    liquid_oxidizer_volume,
    loaded_mass,
    mass_fraction_from_volume_fraction,
    oxidizer_mass_flow,
    oxidizer_loaded_mass,
    oxidizer_required_mass,
    propellant_mass,
    regression_rate_from_gox,
    select_manual_override,
    tank_volume_from_fill_fraction,
    throat_area_from_mass_flow,
    total_mass_flow_from_thrust,
)
from blowdown_hybrid.hydraulics import feed_pressure_drop_pa
from blowdown_hybrid.models import (
    DesignPoint,
    FeedConfig,
    GrainConfig,
    InjectorConfig,
    NozzleConfig,
    SimulationConfig,
    TankConfig,
)
from blowdown_hybrid.solver import simulate
from blowdown_hybrid.thermo import (
    initial_tank_state_from_mass_and_temperature,
    initial_tank_state_from_temperature,
)


def select_seed_case(cases):
    if not cases:
        raise ValueError("No CEA cases are available to seed the blowdown model.")
    return max(cases, key=lambda row: row["isp_s"])


def design_point_from_cea_case(case):
    chamber_pressure_pa = float(case["pc_bar"]) * 1e5
    design_point = DesignPoint(
        mdot_total_kg_s=float(case["mdot_total_kg_s"]),
        of_ratio=float(case["of"]),
        chamber_pressure_pa=chamber_pressure_pa,
    )
    nozzle = NozzleConfig(
        throat_area_m2=float(case["at_m2"]),
        exit_area_m2=float(case["ae_m2"]),
        cstar_mps=float(case["cstar_mps"]),
        cf=float(case["cf"]),
    )
    return design_point, nozzle


def _build_first_pass_design(config, seed_case):
    """Return first-pass sizing data and selected override sources before time marching."""
    ui_mode = config["ui_mode"]
    is_advanced = ui_mode == UI_MODE_ADVANCED

    target_thrust_n = float(seed_case["target_thrust_n"])
    of_ratio = float(seed_case["of"])
    isp_s = float(seed_case["isp_s"])
    chamber_pressure_pa = float(seed_case["pc_bar"]) * 1e5
    oxidizer_temp_k = float(config["tank"]["initial_temp_k"])
    seed_oxidizer_temp_k = float(seed_case["oxidizer_temp_k"])
    fuel_temp_k = float(seed_case["fuel_temp_k"])
    abs_vol_frac = float(seed_case["abs_vol_frac"])
    nozzle_cstar_mps = float(seed_case["cstar_mps"])
    nozzle_cf = float(seed_case["cf"])
    nozzle_exit_area_m2 = float(seed_case["ae_m2"])

    simulation = SimulationConfig(**config["simulation"])
    burn_time_s = simulation.burn_time_s

    tank_sat_state = initial_tank_state_from_temperature(oxidizer_temp_k)
    oxidizer_liquid_density_kg_m3 = tank_sat_state.rho_l_kg_m3
    usable_oxidizer_fraction = (
        config["tank"]["usable_oxidizer_fraction"]
        if is_advanced
        else PROJECT_DEFAULT_USABLE_OXIDIZER_FRACTION
    )
    fuel_usable_fraction = (
        config["grain"]["fuel_usable_fraction"]
        if is_advanced
        else PROJECT_DEFAULT_FUEL_USABLE_FRACTION
    )
    injector_cd = config["injector"]["cd"] if is_advanced else PROJECT_DEFAULT_INJECTOR_CD
    injector_hole_count = config["injector"]["hole_count"] if is_advanced else PROJECT_DEFAULT_INJECTOR_HOLE_COUNT
    port_count = config["grain"]["port_count"] if is_advanced else PROJECT_DEFAULT_PORT_COUNT
    regression_a_si, regression_n, regression_source = regression_parameters_for_mode(config)

    mdot_total_kg_s = total_mass_flow_from_thrust(target_thrust_n, isp_s)
    mdot_ox_kg_s = oxidizer_mass_flow(mdot_total_kg_s, of_ratio)
    mdot_f_kg_s = fuel_mass_flow(mdot_total_kg_s, of_ratio)

    m_ox_required_kg = oxidizer_required_mass(mdot_ox_kg_s, burn_time_s)
    m_f_required_kg = propellant_mass(mdot_f_kg_s, burn_time_s)
    m_ox_loaded_kg = oxidizer_loaded_mass(m_ox_required_kg, usable_oxidizer_fraction)
    m_f_loaded_kg = loaded_mass(m_f_required_kg, fuel_usable_fraction)

    fuel_density_kg_m3 = blend_density_from_volume_fraction(
        abs_vol_frac,
        config["grain"]["abs_density_kg_m3"],
        config["grain"]["paraffin_density_kg_m3"],
    )
    abs_mass_frac = mass_fraction_from_volume_fraction(
        abs_vol_frac,
        config["grain"]["abs_density_kg_m3"],
        config["grain"]["paraffin_density_kg_m3"],
    )

    oxidizer_liquid_volume_m3 = liquid_oxidizer_volume(m_ox_loaded_kg, oxidizer_liquid_density_kg_m3)
    derived_tank_volume_m3 = tank_volume_from_fill_fraction(oxidizer_liquid_volume_m3, config["tank"]["initial_fill_fraction"])
    tank_volume_m3, tank_volume_source = select_manual_override(
        derived_tank_volume_m3,
        config["tank"]["volume_m3"],
        is_advanced and config["tank"]["override_mass_volume"],
        "tank volume",
    )
    tank_initial_mass_kg, tank_mass_source = select_manual_override(
        m_ox_loaded_kg,
        config["tank"]["initial_mass_kg"],
        is_advanced and config["tank"]["override_mass_volume"],
        "tank initial mass",
    )
    tank_initial_temp_k = config["tank"]["initial_temp_k"]

    target_initial_gox_kg_m2_s = config["grain"]["target_initial_gox_kg_m2_s"]
    derived_initial_port_radius_m = initial_port_radius_from_target_gox(
        mdot_ox_kg_s,
        port_count,
        target_initial_gox_kg_m2_s,
    )
    initial_port_radius_m, initial_port_source = select_manual_override(
        derived_initial_port_radius_m,
        config["grain"]["initial_port_radius_m"],
        is_advanced and config["grain"]["override_initial_port_radius"],
        "initial port radius",
    )
    initial_port_diameter_m = 2.0 * initial_port_radius_m
    initial_port_area_m2 = initial_total_port_area(mdot_ox_kg_s, target_initial_gox_kg_m2_s)
    initial_regression_rate_m_s = regression_rate_from_gox(
        regression_a_si,
        regression_n,
        target_initial_gox_kg_m2_s,
    )

    derived_grain_length_m = grain_length_from_fuel_mass_flow(
        mdot_f_kg_s,
        fuel_density_kg_m3,
        port_count,
        initial_port_diameter_m,
        initial_regression_rate_m_s,
    )
    grain_length_m, grain_length_source = select_manual_override(
        derived_grain_length_m,
        config["grain"]["grain_length_m"],
        is_advanced and config["grain"]["override_grain_length"],
        "grain length",
    )

    derived_outer_radius_m = grain_outer_radius_from_loaded_fuel_mass(
        m_f_loaded_kg,
        fuel_density_kg_m3,
        port_count,
        grain_length_m,
        initial_port_radius_m,
    )
    outer_radius_m, outer_radius_source = select_manual_override(
        derived_outer_radius_m,
        config["grain"]["outer_radius_m"],
        is_advanced and config["grain"]["override_outer_radius"],
        "outer grain radius",
    )
    if outer_radius_m is not None and outer_radius_m <= initial_port_radius_m:
        raise ValueError("Outer grain radius must be greater than the initial port radius.")

    if is_advanced:
        injector_delta_p_pa = (
            config["injector"]["delta_p_pa"]
            if config["injector"]["delta_p_mode"] == INJECTOR_DELTA_P_MODE_EXPLICIT
            else injector_delta_p_from_fraction_of_pc(
                config["injector"]["delta_p_fraction_of_pc"],
                chamber_pressure_pa,
            )
        )
        injector_delta_p_source = "advanced_manual"
        injector_delta_p_mode = config["injector"]["delta_p_mode"]
    else:
        injector_delta_p_fraction, injector_delta_p_source = injector_pressure_drop_fraction_for_mode(config)
        injector_delta_p_pa = injector_delta_p_from_fraction_of_pc(injector_delta_p_fraction, chamber_pressure_pa)
        injector_delta_p_mode = "policy_fraction_of_pc"
    derived_injector_total_area_m2 = injector_total_area_from_mass_flow(
        mdot_ox_kg_s,
        injector_cd,
        oxidizer_liquid_density_kg_m3,
        injector_delta_p_pa,
    )
    injector_total_area_m2, injector_area_source = select_manual_override(
        derived_injector_total_area_m2,
        config["injector"]["total_area_m2"],
        is_advanced and config["injector"]["override_total_area"],
        "injector total area",
    )
    injector_hole_diameter_m = equivalent_injector_hole_diameter(
        injector_total_area_m2,
        injector_hole_count,
    )

    throat_area_m2 = throat_area_from_mass_flow(
        mdot_total_kg_s,
        nozzle_cstar_mps,
        chamber_pressure_pa,
    )

    # Keep the seeded expansion ratio while regenerating throat area from the requested thrust/Isp.
    ae_at = nozzle_exit_area_m2 / float(seed_case["at_m2"])
    nozzle = NozzleConfig(
        throat_area_m2=throat_area_m2,
        exit_area_m2=throat_area_m2 * ae_at,
        cstar_mps=nozzle_cstar_mps,
        cf=nozzle_cf,
    )

    tank = TankConfig(
        volume_m3=tank_volume_m3,
        initial_mass_kg=tank_initial_mass_kg,
        initial_temp_k=tank_initial_temp_k,
    )
    feed = FeedConfig(**config["feed"])
    injector = InjectorConfig(
        cd=injector_cd,
        total_area_m2=injector_total_area_m2,
        hole_count=injector_hole_count,
    )
    grain = GrainConfig(
        fuel_density_kg_m3=fuel_density_kg_m3,
        a_reg_si=regression_a_si,
        n_reg=regression_n,
        port_count=port_count,
        initial_port_radius_m=initial_port_radius_m,
        grain_length_m=grain_length_m,
        outer_radius_m=outer_radius_m,
    )
    design_point = DesignPoint(
        mdot_total_kg_s=mdot_total_kg_s,
        of_ratio=of_ratio,
        chamber_pressure_pa=chamber_pressure_pa,
    )

    tank_init, _ = initial_tank_state_from_mass_and_temperature(tank)
    design_feed_pressure_drop_pa = feed_pressure_drop_pa(mdot_ox_kg_s, tank_init.rho_l_kg_m3, feed)
    design_injector_inlet_pressure_pa = tank_init.p_pa - design_feed_pressure_drop_pa
    design_injector_delta_p_pa = design_injector_inlet_pressure_pa - design_point.chamber_pressure_pa

    return {
        "design_point": design_point,
        "nozzle": nozzle,
        "tank": tank,
        "feed": feed,
        "injector": injector,
        "grain": grain,
        "simulation": simulation,
        "tank_initial_state": tank_init,
        "derived": {
            "model_name": "Preliminary 0D Blowdown Simulation",
            "ui_mode": ui_mode,
            "seed_target_thrust_n": target_thrust_n,
            "seed_isp_s": isp_s,
            "seed_of_ratio": of_ratio,
            "seed_pc_bar": chamber_pressure_pa / 1e5,
            "seed_oxidizer_temp_k": seed_oxidizer_temp_k,
            "seed_fuel_temp_k": fuel_temp_k,
            "seed_abs_volume_fraction": abs_vol_frac,
            "seed_abs_mass_fraction": abs_mass_frac,
            "abs_density_kg_m3": config["grain"]["abs_density_kg_m3"],
            "paraffin_density_kg_m3": config["grain"]["paraffin_density_kg_m3"],
            "target_mdot_total_kg_s": mdot_total_kg_s,
            "target_mdot_ox_kg_s": mdot_ox_kg_s,
            "target_mdot_f_kg_s": mdot_f_kg_s,
            "target_of_ratio": of_ratio,
            "target_pc_bar": chamber_pressure_pa / 1e5,
            "required_oxidizer_mass_kg": m_ox_required_kg,
            "loaded_oxidizer_mass_kg": m_ox_loaded_kg,
            "required_fuel_mass_kg": m_f_required_kg,
            "loaded_fuel_mass_kg": m_f_loaded_kg,
            "fuel_density_kg_m3": fuel_density_kg_m3,
            "tank_initial_fill_fraction": config["tank"]["initial_fill_fraction"],
            "tank_usable_oxidizer_fraction": usable_oxidizer_fraction,
            "tank_volume_l": tank_volume_m3 * 1000.0,
            "tank_initial_mass_kg": tank_initial_mass_kg,
            "tank_initial_temp_k": tank_initial_temp_k,
            "tank_initial_pressure_bar": tank_sat_state.p_pa / 1e5,
            "tank_mass_volume_source": tank_mass_source,
            "tank_volume_source": tank_volume_source,
            "tank_usable_fraction_source": "advanced_manual" if is_advanced else "project_default",
            "tank_oxidizer_liquid_volume_l": oxidizer_liquid_volume_m3 * 1000.0,
            "target_initial_gox_kg_m2_s": target_initial_gox_kg_m2_s,
            "initial_port_area_mm2": initial_port_area_m2 * 1e6,
            "initial_port_radius_mm": initial_port_radius_m * 1e3,
            "initial_port_source": initial_port_source,
            "initial_regression_rate_mm_s": initial_regression_rate_m_s * 1e3,
            "grain_length_m": grain_length_m,
            "grain_length_source": grain_length_source,
            "grain_outer_radius_mm": None if outer_radius_m is None else outer_radius_m * 1e3,
            "outer_radius_source": outer_radius_source,
            "fuel_usable_fraction": fuel_usable_fraction,
            "fuel_usable_fraction_source": "advanced_manual" if is_advanced else "project_default",
            "regression_preset": config["grain"]["regression_preset"],
            "regression_a_si": regression_a_si,
            "regression_n": regression_n,
            "regression_source": regression_source,
            "port_count": port_count,
            "port_count_source": "advanced_manual" if is_advanced else "project_default",
            "injector_cd": injector_cd,
            "injector_cd_source": "advanced_manual" if is_advanced else "project_default",
            "injector_hole_count": injector_hole_count,
            "injector_hole_count_source": "advanced_manual" if is_advanced else "project_default",
            "injector_pressure_drop_policy": config["injector"]["pressure_drop_policy"],
            "injector_delta_p_mode": injector_delta_p_mode,
            "injector_delta_p_source": injector_delta_p_source,
            "injector_delta_p_fraction_of_pc": config["injector"]["delta_p_fraction_of_pc"],
            "injector_delta_p_bar": injector_delta_p_pa / 1e5,
            "injector_total_area_mm2": injector_total_area_m2 * 1e6,
            "injector_total_area_source": injector_area_source,
            "injector_area_per_hole_mm2": injector_total_area_m2 / injector.hole_count * 1e6,
            "injector_hole_diameter_mm": injector_hole_diameter_m * 1e3,
            "feed_line_id_mm": feed.line_id_m * 1e3,
            "feed_line_length_m": feed.line_length_m,
            "feed_friction_factor": feed.friction_factor,
            "feed_minor_loss_k_total": feed.minor_loss_k_total,
            "nozzle_throat_area_mm2": nozzle.throat_area_m2 * 1e6,
            "nozzle_exit_area_mm2": nozzle.exit_area_m2 * 1e6,
            "nozzle_cstar_mps": nozzle.cstar_mps,
            "nozzle_cf": nozzle.cf,
            "design_tank_pressure_bar": tank_init.p_pa / 1e5,
            "design_liquid_density_kg_m3": tank_init.rho_l_kg_m3,
            "design_injector_inlet_pressure_bar": design_injector_inlet_pressure_pa / 1e5,
            "design_feed_pressure_drop_bar": design_feed_pressure_drop_pa / 1e5,
            "design_injector_delta_p_bar": design_injector_delta_p_pa / 1e5,
            "simulation_burn_time_s": simulation.burn_time_s,
            "simulation_dt_s": simulation.dt_s,
            "simulation_ambient_pressure_bar": simulation.ambient_pressure_pa / 1e5,
            "simulation_max_inner_iterations": simulation.max_inner_iterations,
            "simulation_relaxation": simulation.relaxation,
            "simulation_relative_tolerance": simulation.relative_tolerance,
            "simulation_tank_quality_cutoff": simulation.stop_when_tank_quality_exceeds,
            "override_active": is_advanced and any(
                [
                    config["tank"]["override_mass_volume"],
                    config["injector"]["override_total_area"],
                    config["grain"]["override_initial_port_radius"],
                    config["grain"]["override_grain_length"],
                    config["grain"]["override_outer_radius"],
                ]
            ),
        },
    }


def build_runtime_inputs(config, seed_case):
    config = build_config(config)
    return {
        "config": config,
        **_build_first_pass_design(config, seed_case),
    }


def run_blowdown(config, seed_case, progress_callback=None, cancel_event=None):
    runtime = build_runtime_inputs(config, seed_case)
    simulation = simulate(
        tank_cfg=runtime["tank"],
        feed_cfg=runtime["feed"],
        injector_cfg=runtime["injector"],
        grain_cfg=runtime["grain"],
        nozzle_cfg=runtime["nozzle"],
        sim_cfg=runtime["simulation"],
        initial_mdot_ox_guess_kg_s=runtime["derived"]["target_mdot_ox_kg_s"],
        initial_pc_guess_pa=runtime["design_point"].chamber_pressure_pa,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
    )
    return {
        **runtime,
        "history": simulation["history"],
        "step_count": simulation["step_count"],
        "target_step_count": simulation["target_step_count"],
        "stop_reason": simulation["stop_reason"],
    }
