"""High-level orchestration for the integrated preliminary 0D blowdown model."""

from __future__ import annotations

from .config import (
    build_config,
    injector_pressure_drop_fraction_for_mode,
    regression_parameters_for_mode,
)
from .constants import (
    INJECTOR_DELTA_P_MODE_EXPLICIT,
    UI_MODE_ADVANCED,
)
from .defaults import (
    PROJECT_DEFAULT_FUEL_USABLE_FRACTION,
    PROJECT_DEFAULT_INJECTOR_CD,
    PROJECT_DEFAULT_INJECTOR_HOLE_DIAMETER_M,
    PROJECT_DEFAULT_INJECTOR_HOLE_COUNT,
    PROJECT_DEFAULT_PORT_COUNT,
    PROJECT_DEFAULT_USABLE_OXIDIZER_FRACTION,
)
from .first_pass import (
    blend_density_from_volume_fraction,
    equivalent_injector_hole_diameter,
    fuel_mass_flow,
    grain_length_from_fuel_mass_flow,
    grain_outer_radius_from_loaded_fuel_mass,
    initial_port_radius_from_target_gox,
    initial_total_port_area,
    injector_delta_p_from_fraction_of_pc,
    injector_hole_count_from_total_area,
    injector_total_area_from_mass_flow,
    injector_total_area_from_hole_count_and_diameter,
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
from .hydraulics import feed_pressure_drop_pa
from .models import (
    DesignPoint,
    FeedConfig,
    GrainConfig,
    InjectorConfig,
    NozzleConfig,
    SimulationConfig,
    TankConfig,
)
from .solver import simulate
from .thermo import (
    initial_tank_state_from_mass_and_temperature,
    initial_tank_state_from_temperature,
)
from src.analysis.geometry_checks import evaluate_grain_geometry
from src.analysis.pressure_budget import pressure_budget
from src.models.nozzle import STANDARD_SEA_LEVEL_PRESSURE_PA, cf_vac_from_isp_and_cstar, evaluate_nozzle_performance


def select_seed_case(cases):
    if not cases:
        raise ValueError("No CEA cases are available to seed the blowdown model.")
    return max(cases, key=lambda row: row["isp_s"])


def design_point_from_cea_case(case):
    chamber_pressure_pa = float(case["pc_bar"]) * 1e5
    cf_sea_level = float(case.get("cf_sea_level", case.get("cf_actual", case["cf"])))
    ae_at = float(case["ae_m2"]) / float(case["at_m2"])
    cf_vac = float(
        case.get(
            "cf_vac",
            cf_vac_from_isp_and_cstar(case["isp_vac_s"], case["cstar_mps"])
            if "isp_vac_s" in case
            else cf_sea_level + (STANDARD_SEA_LEVEL_PRESSURE_PA / chamber_pressure_pa) * ae_at,
        )
    )
    design_point = DesignPoint(
        mdot_total_kg_s=float(case["mdot_total_kg_s"]),
        of_ratio=float(case["of"]),
        chamber_pressure_pa=chamber_pressure_pa,
    )
    nozzle = NozzleConfig(
        throat_area_m2=float(case["at_m2"]),
        exit_area_m2=float(case["ae_m2"]),
        cstar_mps=float(case["cstar_mps"]),
        cf=cf_sea_level,
        cf_vac=cf_vac,
        exit_pressure_ratio=float(case["pe_bar"]) / float(case["pc_bar"]),
        gamma_e=float(case.get("gamma_e", 0.0)) if case.get("gamma_e") is not None else None,
        molecular_weight_exit=float(case.get("mw_e", 0.0)) if case.get("mw_e") is not None else None,
    )
    return design_point, nozzle


def _seed_performance_summary(seed_case, mdot_total_kg_s, chamber_pressure_pa, throat_area_m2, exit_area_m2):
    cf_sea_level = float(seed_case.get("cf_sea_level", seed_case.get("cf_actual", seed_case["cf"])))
    ae_at = float(exit_area_m2) / float(throat_area_m2)
    cf_vac_default = cf_sea_level + (STANDARD_SEA_LEVEL_PRESSURE_PA / float(chamber_pressure_pa)) * ae_at
    cf_vac = float(
        seed_case.get(
            "cf_vac",
            cf_vac_from_isp_and_cstar(seed_case["isp_vac_s"], seed_case["cstar_mps"])
            if "isp_vac_s" in seed_case
            else cf_vac_default,
        )
    )
    nozzle = evaluate_nozzle_performance(
        cstar_mps=float(seed_case["cstar_mps"]),
        cf_vac=cf_vac,
        chamber_pressure_pa=chamber_pressure_pa,
        throat_area_m2=throat_area_m2,
        mdot_total_kg_s=mdot_total_kg_s,
        ambient_pressure_pa=STANDARD_SEA_LEVEL_PRESSURE_PA,
        exit_area_m2=exit_area_m2,
        exit_pressure_ratio=float(seed_case.get("pe_bar", seed_case["pc_bar"])) / float(seed_case["pc_bar"]),
        gamma_e=float(seed_case.get("gamma_e", 0.0)) if seed_case.get("gamma_e") is not None else None,
        molecular_weight_exit=float(seed_case.get("mw_e", 0.0)) if seed_case.get("mw_e") is not None else None,
    )
    return {
        "cf_sea_level": cf_sea_level,
        "cf_vac": cf_vac,
        "cf_ideal": cf_vac,
        "thrust_sea_level_n": nozzle.thrust_actual_n,
        "thrust_vac_n": nozzle.thrust_vac_n,
        "thrust_ideal_vac_n": nozzle.thrust_vac_n,
        "isp_sea_level_s": nozzle.isp_actual_s,
        "isp_vac_s": nozzle.isp_vac_s,
    }


def _build_first_pass_design(config, seed_case, *, performance_lookup=None):
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
    seed_performance = _seed_performance_summary(
        seed_case,
        mdot_total_kg_s=total_mass_flow_from_thrust(target_thrust_n, isp_s),
        chamber_pressure_pa=chamber_pressure_pa,
        throat_area_m2=float(seed_case["at_m2"]),
        exit_area_m2=float(seed_case["ae_m2"]),
    )
    nozzle_cf = seed_performance["cf_sea_level"]
    nozzle_cf_vac = seed_performance["cf_vac"]
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
    injector_hole_diameter_m = (
        config["injector"]["hole_diameter_m"] if is_advanced else PROJECT_DEFAULT_INJECTOR_HOLE_DIAMETER_M
    )
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

    geometry_validation = evaluate_grain_geometry(
        port_radius_initial_m=initial_port_radius_m,
        grain_outer_radius_m=outer_radius_m,
        grain_length_m=grain_length_m,
        port_count=port_count,
        min_radial_web_m=config.get("geometry_policy", {}).get("min_radial_web_m", 0.003),
        min_burnout_web_m=config.get("geometry_policy", {}).get("min_burnout_web_m", 0.001),
        max_port_to_outer_radius_ratio=config.get("geometry_policy", {}).get("max_port_to_outer_radius_ratio", 0.95),
        max_grain_slenderness_ratio=config.get("geometry_policy", {}).get("max_grain_slenderness_ratio", 18.0),
    )

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
    required_injector_total_area_m2, injector_area_source = select_manual_override(
        derived_injector_total_area_m2,
        config["injector"]["total_area_m2"],
        is_advanced and config["injector"]["override_total_area"],
        "injector total area",
    )
    injector_hole_count = injector_hole_count_from_total_area(
        required_injector_total_area_m2,
        injector_hole_diameter_m,
    )
    injector_total_area_m2 = injector_total_area_from_hole_count_and_diameter(
        injector_hole_count,
        injector_hole_diameter_m,
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
        cf_vac=nozzle_cf_vac,
        exit_pressure_ratio=float(seed_case.get("pe_bar", seed_case["pc_bar"])) / float(seed_case["pc_bar"]),
        performance_lookup=performance_lookup,
        gamma_e=float(seed_case.get("gamma_e", 0.0)) if seed_case.get("gamma_e") is not None else None,
        molecular_weight_exit=float(seed_case.get("mw_e", 0.0)) if seed_case.get("mw_e") is not None else None,
    )

    reserve_mass_kg = max(float(tank_initial_mass_kg) * (1.0 - float(usable_oxidizer_fraction)), 0.0)
    tank = TankConfig(
        volume_m3=tank_volume_m3,
        initial_mass_kg=tank_initial_mass_kg,
        initial_temp_k=tank_initial_temp_k,
        reserve_mass_kg=reserve_mass_kg,
    )
    feed = FeedConfig(**config["feed"])
    injector = InjectorConfig(
        cd=injector_cd,
        total_area_m2=injector_total_area_m2,
        hole_count=injector_hole_count,
        minimum_dp_over_pc=float(config["injector"]["minimum_dp_over_pc"]),
        sizing_condition=str(config["injector"]["sizing_condition"]),
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
    design_pressure_budget = pressure_budget(
        tank_pressure_pa=tank_init.p_pa,
        feed_pressure_drop_pa=design_feed_pressure_drop_pa,
        injector_inlet_pressure_pa=design_injector_inlet_pressure_pa,
        injector_delta_p_pa=design_injector_delta_p_pa,
        chamber_pressure_pa=design_point.chamber_pressure_pa,
    )

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
            "seed_isp_sl_s": seed_performance["isp_sea_level_s"],
            "seed_isp_vac_s": seed_performance["isp_vac_s"],
            "seed_of_ratio": of_ratio,
            "seed_pc_bar": chamber_pressure_pa / 1e5,
            "seed_oxidizer_temp_k": seed_oxidizer_temp_k,
            "seed_fuel_temp_k": fuel_temp_k,
            "seed_abs_volume_fraction": abs_vol_frac,
            "seed_abs_mass_fraction": abs_mass_frac,
            "seed_cf_sea_level": seed_performance["cf_sea_level"],
            "seed_cf_vac": seed_performance["cf_vac"],
            "seed_cstar_mps": nozzle_cstar_mps,
            "seed_thrust_sea_level_n": seed_performance["thrust_sea_level_n"],
            "seed_thrust_vac_n": seed_performance["thrust_vac_n"],
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
            "tank_reserve_mass_kg": reserve_mass_kg,
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
            "injector_hole_count_source": "derived_from_total_area_and_fixed_hole_diameter",
            "injector_hole_diameter_mm": injector_hole_diameter_m * 1e3,
            "injector_hole_diameter_source": "advanced_manual" if is_advanced else "project_default",
            "injector_pressure_drop_policy": config["injector"]["pressure_drop_policy"],
            "injector_sizing_condition": config["injector"]["sizing_condition"],
            "injector_minimum_dp_over_pc": config["injector"]["minimum_dp_over_pc"],
            "injector_delta_p_mode": injector_delta_p_mode,
            "injector_delta_p_source": injector_delta_p_source,
            "injector_delta_p_fraction_of_pc": config["injector"]["delta_p_fraction_of_pc"],
            "injector_delta_p_bar": injector_delta_p_pa / 1e5,
            "injector_total_area_mm2": injector_total_area_m2 * 1e6,
            "injector_required_total_area_mm2": required_injector_total_area_m2 * 1e6,
            "injector_total_area_source": injector_area_source,
            "injector_area_per_hole_mm2": injector_total_area_m2 / injector.hole_count * 1e6,
            "feed_line_id_mm": feed.line_id_m * 1e3,
            "feed_line_length_m": feed.line_length_m,
            "feed_friction_factor": feed.friction_factor,
            "feed_minor_loss_k_total": feed.minor_loss_k_total,
            "feed_loss_model": feed.loss_model,
            "feed_pressure_drop_multiplier": feed.pressure_drop_multiplier,
            "feed_manual_delta_p_bar": feed.manual_delta_p_pa / 1e5,
            "feed_loss_source": "manual_override" if feed.loss_model == "manual_override" else (
                "hydraulic_lumped_k_calibrated" if abs(feed.pressure_drop_multiplier - 1.0) > 1e-12 else "hydraulic_lumped_k"
            ),
            "nozzle_throat_area_mm2": nozzle.throat_area_m2 * 1e6,
            "nozzle_exit_area_mm2": nozzle.exit_area_m2 * 1e6,
            "nozzle_cstar_mps": nozzle.cstar_mps,
            "nozzle_cf_sea_level": nozzle.cf,
            "nozzle_cf_vac": nozzle.cf_vac,
            "design_tank_pressure_bar": tank_init.p_pa / 1e5,
            "design_liquid_density_kg_m3": tank_init.rho_l_kg_m3,
            "design_injector_inlet_pressure_bar": design_injector_inlet_pressure_pa / 1e5,
            "design_feed_pressure_drop_bar": design_feed_pressure_drop_pa / 1e5,
            "design_injector_delta_p_bar": design_injector_delta_p_pa / 1e5,
            "design_dp_feed_over_pc": design_pressure_budget["dp_feed_over_pc"],
            "design_dp_injector_over_pc": design_pressure_budget["dp_injector_over_pc"],
            "design_dp_total_over_ptank": design_pressure_budget["dp_total_over_ptank"],
            "design_injector_to_feed_dp_ratio": design_pressure_budget["injector_to_feed_dp_ratio"],
            "design_injector_dominant": design_pressure_budget["injector_delta_p_pa"] >= design_pressure_budget["feed_pressure_drop_pa"],
            "geometry_valid": geometry_validation["valid"],
            "geometry_warnings": geometry_validation["warnings"],
            "geometry_suggestions": geometry_validation["suggestions"],
            "initial_radial_web_mm": geometry_validation["radial_web_m"] * 1e3,
            "initial_port_to_outer_radius_ratio": geometry_validation["port_to_outer_radius_ratio"],
            "grain_slenderness_ratio": geometry_validation["grain_slenderness_ratio"],
            "simulation_burn_time_s": simulation.burn_time_s,
            "simulation_dt_s": simulation.dt_s,
            "simulation_ambient_pressure_bar": simulation.ambient_pressure_pa / 1e5,
            "simulation_max_inner_iterations": simulation.max_inner_iterations,
            "simulation_relaxation": simulation.relaxation,
            "simulation_relative_tolerance": simulation.relative_tolerance,
            "simulation_tank_quality_cutoff": simulation.stop_when_tank_quality_exceeds,
            "simulation_oxidizer_depletion_policy": simulation.oxidizer_depletion_policy,
            "simulation_stop_on_quality_limit": simulation.stop_on_quality_limit,
            "performance_lookup_active": performance_lookup is not None,
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


def build_runtime_inputs(config, seed_case, *, include_performance_lookup=False, lookup_config=None, raw_cea_config=None):
    config = build_config(config)
    performance_lookup = None
    performance_lookup_warning = None
    if include_performance_lookup:
        from src.simulation.performance_lookup import build_performance_lookup

        try:
            performance_lookup = build_performance_lookup(seed_case, lookup_config, raw_cea_config)
        except Exception as exc:
            if bool((lookup_config or {}).get("fallback_to_seed_on_failure", True)):
                performance_lookup_warning = str(exc)
            else:
                raise
    runtime = {
        "config": config,
        **_build_first_pass_design(config, seed_case, performance_lookup=performance_lookup),
    }
    runtime["derived"]["performance_lookup_warning"] = performance_lookup_warning
    runtime["derived"]["performance_lookup_active"] = performance_lookup is not None
    return runtime


def run_blowdown(config, seed_case, progress_callback=None, cancel_event=None):
    runtime = build_runtime_inputs(config, seed_case, include_performance_lookup=True)
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

