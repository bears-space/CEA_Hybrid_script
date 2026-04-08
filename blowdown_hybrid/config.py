"""Configuration loading and validation for the preliminary 0D blowdown model."""

from __future__ import annotations

import math

from cea_hybrid.config import ensure_finite

from blowdown_hybrid.constants import (
    INJECTOR_DELTA_P_MODE_EXPLICIT,
    INJECTOR_DELTA_P_MODE_FRACTION_OF_PC,
    SEED_CASE_HIGHEST_ISP,
    UI_MODE_ADVANCED,
    UI_MODE_BASIC,
)


DEFAULT_CONFIG = {
    "auto_run_after_cea": True,
    "ui_mode": UI_MODE_BASIC,
    "seed_case": SEED_CASE_HIGHEST_ISP,
    "tank": {
        "volume_m3": 0.028,
        "initial_mass_kg": 18.0,
        "initial_temp_k": 293.15,
        "usable_oxidizer_fraction": 0.95,
        "initial_fill_fraction": 0.8,
        "override_mass_volume": False,
    },
    "feed": {
        "line_id_m": 0.012,
        "line_length_m": 1.2,
        "friction_factor": 0.02,
        "minor_loss_k_total": 8.0,
    },
    "injector": {
        "cd": 0.8,
        "hole_count": 24,
        "total_area_m2": 7.5e-5,
        "override_total_area": False,
        "delta_p_mode": INJECTOR_DELTA_P_MODE_FRACTION_OF_PC,
        "delta_p_pa": 6.0e5,
        "delta_p_fraction_of_pc": 0.2,
    },
    "grain": {
        "abs_density_kg_m3": 1050.0,
        "paraffin_density_kg_m3": 930.0,
        "a_reg_si": 5.0e-5,
        "n_reg": 0.5,
        "port_count": 1,
        "target_initial_gox_kg_m2_s": 250.0,
        "initial_port_radius_m": 0.022,
        "grain_length_m": 0.45,
        "outer_radius_m": 0.045,
        "fuel_usable_fraction": 0.98,
        "override_initial_port_radius": False,
        "override_grain_length": False,
        "override_outer_radius": False,
    },
    "simulation": {
        "dt_s": 0.02,
        "burn_time_s": 8.0,
        "ambient_pressure_pa": 101325.0,
        "max_inner_iterations": 80,
        "relaxation": 0.35,
        "relative_tolerance": 1e-6,
        "stop_when_tank_quality_exceeds": 0.95,
    },
}


def _merge_defaults(defaults, raw):
    merged = {}
    for key, default_value in defaults.items():
        raw_value = raw.get(key) if isinstance(raw, dict) else None
        if isinstance(default_value, dict):
            merged[key] = _merge_defaults(default_value, raw_value or {})
        else:
            merged[key] = default_value if raw_value is None else raw_value
    return merged


def build_config(raw=None):
    merged = _merge_defaults(DEFAULT_CONFIG, raw or {})
    config = {
        "auto_run_after_cea": bool(merged["auto_run_after_cea"]),
        "ui_mode": merged["ui_mode"],
        "seed_case": merged["seed_case"],
        "tank": {
            "volume_m3": float(merged["tank"]["volume_m3"]),
            "initial_mass_kg": float(merged["tank"]["initial_mass_kg"]),
            "initial_temp_k": float(merged["tank"]["initial_temp_k"]),
            "usable_oxidizer_fraction": float(merged["tank"]["usable_oxidizer_fraction"]),
            "initial_fill_fraction": float(merged["tank"]["initial_fill_fraction"]),
            "override_mass_volume": bool(merged["tank"]["override_mass_volume"]),
        },
        "feed": {
            "line_id_m": float(merged["feed"]["line_id_m"]),
            "line_length_m": float(merged["feed"]["line_length_m"]),
            "friction_factor": float(merged["feed"]["friction_factor"]),
            "minor_loss_k_total": float(merged["feed"]["minor_loss_k_total"]),
        },
        "injector": {
            "cd": float(merged["injector"]["cd"]),
            "hole_count": int(merged["injector"]["hole_count"]),
            "total_area_m2": float(merged["injector"]["total_area_m2"]),
            "override_total_area": bool(merged["injector"]["override_total_area"]),
            "delta_p_mode": merged["injector"]["delta_p_mode"],
            "delta_p_pa": float(merged["injector"]["delta_p_pa"]),
            "delta_p_fraction_of_pc": float(merged["injector"]["delta_p_fraction_of_pc"]),
        },
        "grain": {
            "abs_density_kg_m3": float(merged["grain"]["abs_density_kg_m3"]),
            "paraffin_density_kg_m3": float(merged["grain"]["paraffin_density_kg_m3"]),
            "a_reg_si": float(merged["grain"]["a_reg_si"]),
            "n_reg": float(merged["grain"]["n_reg"]),
            "port_count": int(merged["grain"]["port_count"]),
            "target_initial_gox_kg_m2_s": float(merged["grain"]["target_initial_gox_kg_m2_s"]),
            "initial_port_radius_m": float(merged["grain"]["initial_port_radius_m"]),
            "grain_length_m": float(merged["grain"]["grain_length_m"]),
            "outer_radius_m": (
                None if merged["grain"]["outer_radius_m"] in {None, ""} else float(merged["grain"]["outer_radius_m"])
            ),
            "fuel_usable_fraction": float(merged["grain"]["fuel_usable_fraction"]),
            "override_initial_port_radius": bool(merged["grain"]["override_initial_port_radius"]),
            "override_grain_length": bool(merged["grain"]["override_grain_length"]),
            "override_outer_radius": bool(merged["grain"]["override_outer_radius"]),
        },
        "simulation": {
            "dt_s": float(merged["simulation"]["dt_s"]),
            "burn_time_s": float(merged["simulation"]["burn_time_s"]),
            "ambient_pressure_pa": float(merged["simulation"]["ambient_pressure_pa"]),
            "max_inner_iterations": int(merged["simulation"]["max_inner_iterations"]),
            "relaxation": float(merged["simulation"]["relaxation"]),
            "relative_tolerance": float(merged["simulation"]["relative_tolerance"]),
            "stop_when_tank_quality_exceeds": float(merged["simulation"]["stop_when_tank_quality_exceeds"]),
        },
    }
    validate_config(config)
    return config


def validate_config(config):
    if config["seed_case"] != SEED_CASE_HIGHEST_ISP:
        raise ValueError("Only the highest-Isp CEA seed case is currently supported.")
    if config["ui_mode"] not in {UI_MODE_BASIC, UI_MODE_ADVANCED}:
        raise ValueError("ui_mode must be 'basic' or 'advanced'.")

    for name, value in [
        ("tank.volume_m3", config["tank"]["volume_m3"]),
        ("tank.initial_mass_kg", config["tank"]["initial_mass_kg"]),
        ("tank.initial_temp_k", config["tank"]["initial_temp_k"]),
        ("tank.usable_oxidizer_fraction", config["tank"]["usable_oxidizer_fraction"]),
        ("tank.initial_fill_fraction", config["tank"]["initial_fill_fraction"]),
        ("feed.line_id_m", config["feed"]["line_id_m"]),
        ("feed.line_length_m", config["feed"]["line_length_m"]),
        ("feed.friction_factor", config["feed"]["friction_factor"]),
        ("feed.minor_loss_k_total", config["feed"]["minor_loss_k_total"]),
        ("injector.cd", config["injector"]["cd"]),
        ("injector.total_area_m2", config["injector"]["total_area_m2"]),
        ("injector.delta_p_pa", config["injector"]["delta_p_pa"]),
        ("injector.delta_p_fraction_of_pc", config["injector"]["delta_p_fraction_of_pc"]),
        ("grain.abs_density_kg_m3", config["grain"]["abs_density_kg_m3"]),
        ("grain.paraffin_density_kg_m3", config["grain"]["paraffin_density_kg_m3"]),
        ("grain.a_reg_si", config["grain"]["a_reg_si"]),
        ("grain.n_reg", config["grain"]["n_reg"]),
        ("grain.target_initial_gox_kg_m2_s", config["grain"]["target_initial_gox_kg_m2_s"]),
        ("grain.initial_port_radius_m", config["grain"]["initial_port_radius_m"]),
        ("grain.grain_length_m", config["grain"]["grain_length_m"]),
        ("grain.fuel_usable_fraction", config["grain"]["fuel_usable_fraction"]),
        ("simulation.dt_s", config["simulation"]["dt_s"]),
        ("simulation.burn_time_s", config["simulation"]["burn_time_s"]),
        ("simulation.ambient_pressure_pa", config["simulation"]["ambient_pressure_pa"]),
        ("simulation.relaxation", config["simulation"]["relaxation"]),
        ("simulation.relative_tolerance", config["simulation"]["relative_tolerance"]),
        ("simulation.stop_when_tank_quality_exceeds", config["simulation"]["stop_when_tank_quality_exceeds"]),
    ]:
        ensure_finite(value, name)

    if config["tank"]["volume_m3"] <= 0.0:
        raise ValueError("Tank volume must be positive.")
    if config["tank"]["initial_mass_kg"] <= 0.0:
        raise ValueError("Initial tank mass must be positive.")
    if config["tank"]["initial_temp_k"] <= 0.0:
        raise ValueError("Initial tank temperature must be positive.")
    if not 0.0 < config["tank"]["usable_oxidizer_fraction"] <= 1.0:
        raise ValueError("Usable oxidizer fraction must be in the interval (0, 1].")
    if not 0.0 < config["tank"]["initial_fill_fraction"] < 1.0:
        raise ValueError("Initial fill fraction must be in the interval (0, 1).")

    if config["feed"]["line_id_m"] <= 0.0:
        raise ValueError("Feed line inner diameter must be positive.")
    if config["feed"]["line_length_m"] < 0.0:
        raise ValueError("Feed line length cannot be negative.")
    if config["feed"]["friction_factor"] < 0.0:
        raise ValueError("Feed friction factor cannot be negative.")
    if config["feed"]["minor_loss_k_total"] < 0.0:
        raise ValueError("Feed minor loss K cannot be negative.")

    if config["injector"]["cd"] <= 0.0:
        raise ValueError("Injector discharge coefficient must be positive.")
    if config["injector"]["hole_count"] <= 0:
        raise ValueError("Injector hole count must be positive.")
    if config["injector"]["total_area_m2"] <= 0.0:
        raise ValueError("Manual injector total area must be positive.")
    if config["injector"]["delta_p_mode"] not in {
        INJECTOR_DELTA_P_MODE_EXPLICIT,
        INJECTOR_DELTA_P_MODE_FRACTION_OF_PC,
    }:
        raise ValueError("Unknown injector delta-p mode.")
    if config["injector"]["delta_p_pa"] <= 0.0:
        raise ValueError("Explicit injector delta-p must be positive.")
    if config["injector"]["delta_p_fraction_of_pc"] <= 0.0:
        raise ValueError("Injector delta-p fraction of chamber pressure must be positive.")

    if config["grain"]["abs_density_kg_m3"] <= 0.0:
        raise ValueError("ABS density must be positive.")
    if config["grain"]["paraffin_density_kg_m3"] <= 0.0:
        raise ValueError("Paraffin density must be positive.")
    if config["grain"]["a_reg_si"] <= 0.0:
        raise ValueError("Regression coefficient a must be positive.")
    if config["grain"]["n_reg"] <= 0.0:
        raise ValueError("Regression exponent n must be positive.")
    if config["grain"]["port_count"] <= 0:
        raise ValueError("Port count must be positive.")
    if config["grain"]["target_initial_gox_kg_m2_s"] <= 0.0:
        raise ValueError("Target initial oxidizer flux must be positive.")
    if config["grain"]["initial_port_radius_m"] <= 0.0:
        raise ValueError("Manual initial port radius must be positive.")
    if config["grain"]["grain_length_m"] <= 0.0:
        raise ValueError("Manual grain length must be positive.")
    if config["grain"]["outer_radius_m"] is not None and config["grain"]["outer_radius_m"] <= 0.0:
        raise ValueError("Manual outer grain radius must be positive.")
    if not 0.0 < config["grain"]["fuel_usable_fraction"] <= 1.0:
        raise ValueError("Fuel usable fraction must be in the interval (0, 1].")

    if config["simulation"]["dt_s"] <= 0.0:
        raise ValueError("Simulation time step must be positive.")
    if config["simulation"]["burn_time_s"] <= 0.0:
        raise ValueError("Simulation burn time must be positive.")
    if config["simulation"]["ambient_pressure_pa"] < 0.0:
        raise ValueError("Ambient pressure cannot be negative.")
    if config["simulation"]["max_inner_iterations"] <= 0:
        raise ValueError("Maximum inner iterations must be positive.")
    if not 0.0 < config["simulation"]["relaxation"] <= 1.0:
        raise ValueError("Relaxation must be in the interval (0, 1].")
    if config["simulation"]["relative_tolerance"] <= 0.0:
        raise ValueError("Relative tolerance must be positive.")
    if not 0.0 < config["simulation"]["stop_when_tank_quality_exceeds"] <= 1.0:
        raise ValueError("Tank quality cutoff must be in the interval (0, 1].")


def estimate_total_steps(config):
    return max(1, int(math.ceil(config["simulation"]["burn_time_s"] / config["simulation"]["dt_s"])))
