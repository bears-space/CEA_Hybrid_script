"""Hybrid grain helper functions for the blowdown model."""

import math

from .models import GrainConfig


def total_port_area_m2(port_radius_m: float, port_count: int) -> float:
    return port_count * math.pi * port_radius_m**2


def regression_rate_m_s(mdot_ox_kg_s: float, grain: GrainConfig, port_radius_m: float) -> tuple[float, float]:
    """
    Return the oxidizer flux and regression rate for the current port radius.
    """
    port_area = total_port_area_m2(port_radius_m, grain.port_count)
    if port_area <= 0.0:
        raise ValueError("Port area must remain positive.")
    gox = mdot_ox_kg_s / port_area
    rdot = grain.a_reg_si * gox**grain.n_reg
    return gox, rdot


def fuel_mass_flow_kg_s(mdot_ox_kg_s: float, grain: GrainConfig, port_radius_m: float) -> tuple[float, float, float]:
    """
    Return oxidizer flux, regression rate, and fuel mass flow.
    """
    gox, rdot = regression_rate_m_s(mdot_ox_kg_s, grain, port_radius_m)
    burning_area = grain.port_count * (2.0 * math.pi * port_radius_m * grain.grain_length_m)
    mdot_f = grain.fuel_density_kg_m3 * burning_area * rdot
    return gox, rdot, mdot_f


def required_grain_length_for_target_fuel_flow(
    target_mdot_ox_kg_s: float,
    target_mdot_f_kg_s: float,
    fuel_density_kg_m3: float,
    a_reg_si: float,
    n_reg: float,
    port_count: int,
    initial_port_radius_m: float,
) -> float:
    """
    Solve the grain length required to match the target initial fuel flow.
    """
    port_area = total_port_area_m2(initial_port_radius_m, port_count)
    gox = target_mdot_ox_kg_s / port_area
    rdot = a_reg_si * gox**n_reg
    if rdot <= 0.0:
        raise ValueError("Regression rate must be positive.")
    denominator = fuel_density_kg_m3 * port_count * (2.0 * math.pi * initial_port_radius_m) * rdot
    return target_mdot_f_kg_s / denominator

