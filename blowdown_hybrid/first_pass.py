"""Pure first-pass sizing helpers for the preliminary 0D blowdown model."""

from __future__ import annotations

import math

from blowdown_hybrid.constants import G0_MPS2


def total_mass_flow_from_thrust(target_thrust_n: float, isp_s: float) -> float:
    """Return total propellant mass flow from thrust and specific impulse."""
    if target_thrust_n <= 0.0:
        raise ValueError("target_thrust_n must be positive.")
    if isp_s <= 0.0:
        raise ValueError("isp_s must be positive.")
    return target_thrust_n / (G0_MPS2 * isp_s)


def total_mass_flow_from_pc_at_cstar(
    chamber_pressure_pa: float,
    throat_area_m2: float,
    cstar_mps: float,
) -> float:
    """Return total mass flow from chamber pressure, throat area, and c*."""
    if chamber_pressure_pa <= 0.0:
        raise ValueError("chamber_pressure_pa must be positive.")
    if throat_area_m2 <= 0.0:
        raise ValueError("throat_area_m2 must be positive.")
    if cstar_mps <= 0.0:
        raise ValueError("cstar_mps must be positive.")
    return chamber_pressure_pa * throat_area_m2 / cstar_mps


def oxidizer_mass_flow(mdot_total_kg_s: float, of_ratio: float) -> float:
    """Return oxidizer mass flow from total flow and O/F."""
    if mdot_total_kg_s <= 0.0:
        raise ValueError("mdot_total_kg_s must be positive.")
    if of_ratio <= 0.0:
        raise ValueError("of_ratio must be positive.")
    return (of_ratio / (1.0 + of_ratio)) * mdot_total_kg_s


def fuel_mass_flow(mdot_total_kg_s: float, of_ratio: float) -> float:
    """Return fuel mass flow from total flow and O/F."""
    if mdot_total_kg_s <= 0.0:
        raise ValueError("mdot_total_kg_s must be positive.")
    if of_ratio <= 0.0:
        raise ValueError("of_ratio must be positive.")
    return mdot_total_kg_s / (1.0 + of_ratio)


def propellant_mass(mdot_kg_s: float, burn_time_s: float) -> float:
    """Return consumed propellant mass over the requested burn duration."""
    if mdot_kg_s <= 0.0:
        raise ValueError("mdot_kg_s must be positive.")
    if burn_time_s <= 0.0:
        raise ValueError("burn_time_s must be positive.")
    return mdot_kg_s * burn_time_s


def loaded_mass(required_mass_kg: float, usable_fraction: float) -> float:
    """Return loaded mass from required consumed mass and usable fraction."""
    if required_mass_kg <= 0.0:
        raise ValueError("required_mass_kg must be positive.")
    if not (0.0 < usable_fraction <= 1.0):
        raise ValueError("usable_fraction must be in the interval (0, 1].")
    return required_mass_kg / usable_fraction


def blend_density_from_volume_fraction(
    volume_fraction_component_a: float,
    density_a_kg_m3: float,
    density_b_kg_m3: float,
) -> float:
    """Return blend density from a two-component volume fraction mix."""
    phi_a = volume_fraction_component_a
    if not (0.0 <= phi_a <= 1.0):
        raise ValueError("volume_fraction_component_a must be in the interval [0, 1].")
    if density_a_kg_m3 <= 0.0 or density_b_kg_m3 <= 0.0:
        raise ValueError("component densities must be positive.")
    return 1.0 / (phi_a / density_a_kg_m3 + (1.0 - phi_a) / density_b_kg_m3)


def mass_fraction_from_volume_fraction(
    volume_fraction_component_a: float,
    density_a_kg_m3: float,
    density_b_kg_m3: float,
) -> float:
    """Return the component-A mass fraction from a two-component volume fraction mix."""
    phi_a = volume_fraction_component_a
    if not (0.0 <= phi_a <= 1.0):
        raise ValueError("volume_fraction_component_a must be in the interval [0, 1].")
    if density_a_kg_m3 <= 0.0 or density_b_kg_m3 <= 0.0:
        raise ValueError("component densities must be positive.")
    denominator = phi_a * density_a_kg_m3 + (1.0 - phi_a) * density_b_kg_m3
    if denominator <= 0.0:
        raise ValueError("mixture denominator must be positive.")
    return (phi_a * density_a_kg_m3) / denominator


def tank_volume_from_fill_fraction(
    loaded_oxidizer_mass_kg: float,
    oxidizer_liquid_density_kg_m3: float,
    initial_fill_fraction: float,
) -> float:
    """Return total tank volume from loaded oxidizer mass and liquid fill fraction."""
    if loaded_oxidizer_mass_kg <= 0.0:
        raise ValueError("loaded_oxidizer_mass_kg must be positive.")
    if oxidizer_liquid_density_kg_m3 <= 0.0:
        raise ValueError("oxidizer_liquid_density_kg_m3 must be positive.")
    if not (0.0 < initial_fill_fraction < 1.0):
        raise ValueError("initial_fill_fraction must be in the interval (0, 1).")
    return loaded_oxidizer_mass_kg / (oxidizer_liquid_density_kg_m3 * initial_fill_fraction)


def throat_area_from_mass_flow(
    mdot_total_kg_s: float,
    cstar_mps: float,
    chamber_pressure_pa: float,
) -> float:
    """Return throat area from total mass flow, c*, and chamber pressure."""
    if mdot_total_kg_s <= 0.0:
        raise ValueError("mdot_total_kg_s must be positive.")
    if cstar_mps <= 0.0:
        raise ValueError("cstar_mps must be positive.")
    if chamber_pressure_pa <= 0.0:
        raise ValueError("chamber_pressure_pa must be positive.")
    return mdot_total_kg_s * cstar_mps / chamber_pressure_pa


def initial_total_port_area(mdot_ox_kg_s: float, target_initial_gox_kg_m2_s: float) -> float:
    """Return initial total port flow area from oxidizer mass flow and target Gox."""
    if mdot_ox_kg_s <= 0.0:
        raise ValueError("mdot_ox_kg_s must be positive.")
    if target_initial_gox_kg_m2_s <= 0.0:
        raise ValueError("target_initial_gox_kg_m2_s must be positive.")
    return mdot_ox_kg_s / target_initial_gox_kg_m2_s


def initial_port_radius_from_target_gox(
    mdot_ox_kg_s: float,
    port_count: int,
    target_initial_gox_kg_m2_s: float,
) -> float:
    """Return initial port radius for N identical circular ports at the target Gox."""
    if mdot_ox_kg_s <= 0.0:
        raise ValueError("mdot_ox_kg_s must be positive.")
    if port_count <= 0:
        raise ValueError("port_count must be greater than zero.")
    if target_initial_gox_kg_m2_s <= 0.0:
        raise ValueError("target_initial_gox_kg_m2_s must be positive.")
    return math.sqrt(mdot_ox_kg_s / (math.pi * port_count * target_initial_gox_kg_m2_s))


def regression_rate_from_gox(
    regression_a_si: float,
    regression_n: float,
    target_initial_gox_kg_m2_s: float,
) -> float:
    """Return initial regression rate from the chosen target Gox."""
    if regression_a_si <= 0.0:
        raise ValueError("regression_a_si must be positive.")
    if regression_n <= 0.0:
        raise ValueError("regression_n must be positive.")
    if target_initial_gox_kg_m2_s <= 0.0:
        raise ValueError("target_initial_gox_kg_m2_s must be positive.")
    return regression_a_si * target_initial_gox_kg_m2_s**regression_n


def grain_length_from_fuel_mass_flow(
    mdot_f_kg_s: float,
    fuel_density_kg_m3: float,
    port_count: int,
    initial_port_diameter_m: float,
    initial_regression_rate_m_s: float,
) -> float:
    """Return grain length needed to match the target initial fuel mass flow."""
    if mdot_f_kg_s <= 0.0:
        raise ValueError("mdot_f_kg_s must be positive.")
    if fuel_density_kg_m3 <= 0.0:
        raise ValueError("fuel_density_kg_m3 must be positive.")
    if port_count <= 0:
        raise ValueError("port_count must be greater than zero.")
    if initial_port_diameter_m <= 0.0:
        raise ValueError("initial_port_diameter_m must be positive.")
    if initial_regression_rate_m_s <= 0.0:
        raise ValueError("initial_regression_rate_m_s must be positive.")
    denominator = (
        fuel_density_kg_m3
        * port_count
        * math.pi
        * initial_port_diameter_m
        * initial_regression_rate_m_s
    )
    return mdot_f_kg_s / denominator


def fuel_volume_from_mass(fuel_loaded_mass_kg: float, fuel_density_kg_m3: float) -> float:
    """Return solid fuel volume from loaded mass and density."""
    if fuel_loaded_mass_kg <= 0.0:
        raise ValueError("fuel_loaded_mass_kg must be positive.")
    if fuel_density_kg_m3 <= 0.0:
        raise ValueError("fuel_density_kg_m3 must be positive.")
    return fuel_loaded_mass_kg / fuel_density_kg_m3


def grain_outer_radius_from_loaded_fuel_mass(
    loaded_fuel_mass_kg: float,
    fuel_density_kg_m3: float,
    port_count: int,
    grain_length_m: float,
    initial_port_radius_m: float,
) -> float:
    """Return the outer grain radius required to contain the loaded fuel volume."""
    if port_count <= 0:
        raise ValueError("port_count must be greater than zero.")
    if grain_length_m <= 0.0:
        raise ValueError("grain_length_m must be positive.")
    if initial_port_radius_m <= 0.0:
        raise ValueError("initial_port_radius_m must be positive.")
    fuel_volume_m3 = fuel_volume_from_mass(loaded_fuel_mass_kg, fuel_density_kg_m3)
    return math.sqrt(
        initial_port_radius_m**2 + fuel_volume_m3 / (port_count * math.pi * grain_length_m)
    )


def injector_delta_p_from_fraction_of_pc(
    injector_delta_p_fraction_of_pc: float,
    chamber_pressure_pa: float,
) -> float:
    """Return injector pressure drop from a fraction of chamber pressure."""
    if injector_delta_p_fraction_of_pc <= 0.0:
        raise ValueError("injector_delta_p_fraction_of_pc must be positive.")
    if chamber_pressure_pa <= 0.0:
        raise ValueError("chamber_pressure_pa must be positive.")
    return injector_delta_p_fraction_of_pc * chamber_pressure_pa


def injector_total_area_from_mass_flow(
    mdot_ox_kg_s: float,
    injector_cd: float,
    oxidizer_liquid_density_kg_m3: float,
    injector_delta_p_pa: float,
) -> float:
    """Return the total injector flow area required by the design-point oxidizer flow."""
    if mdot_ox_kg_s <= 0.0:
        raise ValueError("mdot_ox_kg_s must be positive.")
    if injector_cd <= 0.0:
        raise ValueError("injector_cd must be positive.")
    if oxidizer_liquid_density_kg_m3 <= 0.0:
        raise ValueError("oxidizer_liquid_density_kg_m3 must be positive.")
    if injector_delta_p_pa <= 0.0:
        raise ValueError("injector_delta_p_pa must be positive.")
    return mdot_ox_kg_s / (
        injector_cd * math.sqrt(2.0 * oxidizer_liquid_density_kg_m3 * injector_delta_p_pa)
    )


def equivalent_injector_hole_diameter(
    injector_total_area_m2: float,
    injector_hole_count: int,
) -> float:
    """Return equivalent round-hole diameter for the total injector area split evenly."""
    if injector_total_area_m2 <= 0.0:
        raise ValueError("injector_total_area_m2 must be positive.")
    if injector_hole_count <= 0:
        raise ValueError("injector_hole_count must be greater than zero.")
    return math.sqrt(4.0 * injector_total_area_m2 / (math.pi * injector_hole_count))


def select_manual_override(
    derived_value: float,
    manual_value: float | None,
    use_manual: bool,
    label: str,
) -> tuple[float, str]:
    """Return the active value with explicit override precedence."""
    if use_manual:
        if manual_value is None:
            raise ValueError(f"{label} manual override is enabled but no manual value was provided.")
        return manual_value, "manual_override"
    return derived_value, "auto_derived"
