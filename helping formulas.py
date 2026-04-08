from pathlib import Path

script = r'''"""
hybrid_first_pass_formulas.py

Compact first-pass sizing formulas for a hybrid rocket engine.
This script only lists and evaluates the basic algebraic relations.

Inputs you typically choose:
- thrust_n
- burn_time_s
- of_ratio
- isp_s
- chamber_pressure_pa
- cstar_mps
- oxidizer_liquid_density_kg_m3
- fuel_density_kg_m3
- initial_fill_fraction
- port_count
- target_initial_gox_kg_m2_s
- regression_a_si
- regression_n
- injector_cd
- injector_delta_p_pa
- injector_hole_count
- fuel volume fraction and densities for paraffin/ABS blend

Outputs:
- total / oxidizer / fuel mass flow
- required oxidizer / fuel mass
- tank liquid volume / tank total volume
- throat area / throat diameter
- initial port diameter
- initial regression rate
- grain length
- grain outer diameter
- injector total area / equivalent hole diameter
"""

from __future__ import annotations
import math

G0 = 9.80665


def total_mass_flow_from_thrust(thrust_n: float, isp_s: float) -> float:
    """mdot_total = F / (g0 * Isp)"""
    return thrust_n / (G0 * isp_s)


def total_mass_flow_from_pc_at_cstar(
    chamber_pressure_pa: float,
    throat_area_m2: float,
    cstar_mps: float,
) -> float:
    """mdot_total = Pc * At / c*"""
    return chamber_pressure_pa * throat_area_m2 / cstar_mps


def oxidizer_mass_flow(mdot_total_kg_s: float, of_ratio: float) -> float:
    """mdot_ox = (O/F) / (1 + O/F) * mdot_total"""
    return (of_ratio / (1.0 + of_ratio)) * mdot_total_kg_s


def fuel_mass_flow(mdot_total_kg_s: float, of_ratio: float) -> float:
    """mdot_f = 1 / (1 + O/F) * mdot_total"""
    return mdot_total_kg_s / (1.0 + of_ratio)


def propellant_mass(mdot_kg_s: float, burn_time_s: float) -> float:
    """m = mdot * t_b"""
    return mdot_kg_s * burn_time_s


def loaded_mass(required_mass_kg: float, usable_fraction: float) -> float:
    """m_load = m_required / usable_fraction"""
    if not (0.0 < usable_fraction <= 1.0):
        raise ValueError("usable_fraction must be in (0, 1].")
    return required_mass_kg / usable_fraction


def liquid_volume_from_mass(mass_kg: float, liquid_density_kg_m3: float) -> float:
    """V_liquid = m / rho"""
    return mass_kg / liquid_density_kg_m3


def tank_volume_from_fill_fraction(
    oxidizer_loaded_mass_kg: float,
    oxidizer_liquid_density_kg_m3: float,
    initial_fill_fraction: float,
) -> float:
    """V_tank = m_ox_load / (rho_ox_liq * fill_fraction)"""
    if not (0.0 < initial_fill_fraction < 1.0):
        raise ValueError("initial_fill_fraction must be in (0, 1).")
    return oxidizer_loaded_mass_kg / (oxidizer_liquid_density_kg_m3 * initial_fill_fraction)


def throat_area(
    mdot_total_kg_s: float,
    cstar_mps: float,
    chamber_pressure_pa: float,
) -> float:
    """At = mdot_total * c* / Pc"""
    return mdot_total_kg_s * cstar_mps / chamber_pressure_pa


def circular_diameter_from_area(area_m2: float) -> float:
    """d = sqrt(4A/pi)"""
    return math.sqrt(4.0 * area_m2 / math.pi)


def initial_total_port_area(
    mdot_ox_kg_s: float,
    target_initial_gox_kg_m2_s: float,
) -> float:
    """A_port_0 = mdot_ox / Gox_0"""
    return mdot_ox_kg_s / target_initial_gox_kg_m2_s


def initial_port_diameter(
    mdot_ox_kg_s: float,
    port_count: int,
    target_initial_gox_kg_m2_s: float,
) -> float:
    """Dp0 = sqrt(4 * mdot_ox / (pi * Np * Gox_0))"""
    if port_count <= 0:
        raise ValueError("port_count must be > 0.")
    return math.sqrt(4.0 * mdot_ox_kg_s / (math.pi * port_count * target_initial_gox_kg_m2_s))


def regression_rate(
    regression_a_si: float,
    regression_n: float,
    gox_kg_m2_s: float,
) -> float:
    """rdot = a * Gox^n"""
    return regression_a_si * (gox_kg_m2_s ** regression_n)


def grain_length_from_fuel_mass_flow(
    mdot_f_kg_s: float,
    fuel_density_kg_m3: float,
    port_count: int,
    initial_port_diameter_m: float,
    initial_regression_rate_m_s: float,
) -> float:
    """
    mdot_f = rho_f * Np * pi * Dp0 * Lg * rdot0
    -> Lg = mdot_f / (rho_f * Np * pi * Dp0 * rdot0)
    """
    if port_count <= 0:
        raise ValueError("port_count must be > 0.")
    denom = fuel_density_kg_m3 * port_count * math.pi * initial_port_diameter_m * initial_regression_rate_m_s
    return mdot_f_kg_s / denom


def fuel_volume_from_mass(fuel_loaded_mass_kg: float, fuel_density_kg_m3: float) -> float:
    """V_fuel = m_f_load / rho_f"""
    return fuel_loaded_mass_kg / fuel_density_kg_m3


def grain_outer_radius(
    fuel_loaded_mass_kg: float,
    fuel_density_kg_m3: float,
    port_count: int,
    grain_length_m: float,
    initial_port_radius_m: float,
) -> float:
    """
    V_f = Np * pi * (Ro^2 - Ri0^2) * Lg
    -> Ro = sqrt(Ri0^2 + V_f / (Np * pi * Lg))
    """
    if port_count <= 0:
        raise ValueError("port_count must be > 0.")
    fuel_volume_m3 = fuel_volume_from_mass(fuel_loaded_mass_kg, fuel_density_kg_m3)
    return math.sqrt(initial_port_radius_m**2 + fuel_volume_m3 / (port_count * math.pi * grain_length_m))


def injector_total_area(
    mdot_ox_kg_s: float,
    injector_cd: float,
    oxidizer_liquid_density_kg_m3: float,
    injector_delta_p_pa: float,
) -> float:
    """
    A_inj = mdot_ox / (Cd * sqrt(2 * rho_ox * dP_inj))
    """
    return mdot_ox_kg_s / (injector_cd * math.sqrt(2.0 * oxidizer_liquid_density_kg_m3 * injector_delta_p_pa))


def equivalent_injector_hole_diameter(
    injector_total_area_m2: float,
    injector_hole_count: int,
) -> float:
    """
    d_h = sqrt(4 * A_inj_total / (pi * Nh))
    """
    if injector_hole_count <= 0:
        raise ValueError("injector_hole_count must be > 0.")
    return math.sqrt(4.0 * injector_total_area_m2 / (math.pi * injector_hole_count))


def blend_density_from_volume_fraction(
    volume_fraction_component_a: float,
    density_a_kg_m3: float,
    density_b_kg_m3: float,
) -> float:
    """
    rho_blend = 1 / (phi_a/rho_a + (1-phi_a)/rho_b)
    For your case, component_a can be ABS and component_b paraffin.
    """
    phi_a = volume_fraction_component_a
    if not (0.0 <= phi_a <= 1.0):
        raise ValueError("volume_fraction_component_a must be in [0, 1].")
    return 1.0 / (phi_a / density_a_kg_m3 + (1.0 - phi_a) / density_b_kg_m3)


def mass_fraction_from_volume_fraction(
    volume_fraction_component_a: float,
    density_a_kg_m3: float,
    density_b_kg_m3: float,
) -> float:
    """
    w_a = (phi_a * rho_a) / (phi_a * rho_a + (1-phi_a) * rho_b)
    For your case, component_a can be ABS and component_b paraffin.
    """
    phi_a = volume_fraction_component_a
    if not (0.0 <= phi_a <= 1.0):
        raise ValueError("volume_fraction_component_a must be in [0, 1].")
    return (phi_a * density_a_kg_m3) / (phi_a * density_a_kg_m3 + (1.0 - phi_a) * density_b_kg_m3)


if __name__ == "__main__":
    # -----------------------------------------------------------------
    # Example inputs
    # Replace these with your actual values
    # -----------------------------------------------------------------
    thrust_n = 3000.0
    burn_time_s = 8.0
    of_ratio = 7.0
    isp_s = 280.0

    chamber_pressure_pa = 30.0e5
    cstar_mps = 1650.0

    oxidizer_liquid_density_kg_m3 = 750.0
    initial_fill_fraction = 0.80
    oxidizer_usable_fraction = 0.95
    fuel_usable_fraction = 0.98

    port_count = 1
    target_initial_gox_kg_m2_s = 250.0

    regression_a_si = 5.0e-5
    regression_n = 0.5
    injector_cd = 0.80
    injector_delta_p_pa = 6.0e5
    injector_hole_count = 24

    density_abs_kg_m3 = 1040.0
    density_paraffin_kg_m3 = 900.0
    abs_volume_fraction = 0.10

    # -----------------------------------------------------------------
    # Derived fuel blend properties
    # -----------------------------------------------------------------
    fuel_density_kg_m3 = blend_density_from_volume_fraction(
        abs_volume_fraction,
        density_abs_kg_m3,
        density_paraffin_kg_m3,
    )
    abs_mass_fraction = mass_fraction_from_volume_fraction(
        abs_volume_fraction,
        density_abs_kg_m3,
        density_paraffin_kg_m3,
    )

    # -----------------------------------------------------------------
    # Flow and required masses
    # -----------------------------------------------------------------
    mdot_total_kg_s = total_mass_flow_from_thrust(thrust_n, isp_s)
    mdot_ox_kg_s = oxidizer_mass_flow(mdot_total_kg_s, of_ratio)
    mdot_f_kg_s = fuel_mass_flow(mdot_total_kg_s, of_ratio)

    m_ox_required_kg = propellant_mass(mdot_ox_kg_s, burn_time_s)
    m_f_required_kg = propellant_mass(mdot_f_kg_s, burn_time_s)

    m_ox_loaded_kg = loaded_mass(m_ox_required_kg, oxidizer_usable_fraction)
    m_f_loaded_kg = loaded_mass(m_f_required_kg, fuel_usable_fraction)

    # -----------------------------------------------------------------
    # Tank sizing
    # -----------------------------------------------------------------
    oxidizer_liquid_volume_m3 = liquid_volume_from_mass(m_ox_loaded_kg, oxidizer_liquid_density_kg_m3)
    tank_volume_m3 = tank_volume_from_fill_fraction(
        m_ox_loaded_kg,
        oxidizer_liquid_density_kg_m3,
        initial_fill_fraction,
    )

    # -----------------------------------------------------------------
    # Nozzle throat
    # -----------------------------------------------------------------
    throat_area_m2 = throat_area(mdot_total_kg_s, cstar_mps, chamber_pressure_pa)
    throat_diameter_m = circular_diameter_from_area(throat_area_m2)

    # -----------------------------------------------------------------
    # Grain first-pass sizing
    # -----------------------------------------------------------------
    total_port_area_m2 = initial_total_port_area(mdot_ox_kg_s, target_initial_gox_kg_m2_s)
    initial_port_diameter_m = initial_port_diameter(
        mdot_ox_kg_s,
        port_count,
        target_initial_gox_kg_m2_s,
    )
    initial_port_radius_m = 0.5 * initial_port_diameter_m

    initial_rdot_m_s = regression_rate(
        regression_a_si,
        regression_n,
        target_initial_gox_kg_m2_s,
    )

    grain_length_m = grain_length_from_fuel_mass_flow(
        mdot_f_kg_s,
        fuel_density_kg_m3,
        port_count,
        initial_port_diameter_m,
        initial_rdot_m_s,
    )

    grain_outer_radius_m = grain_outer_radius(
        m_f_loaded_kg,
        fuel_density_kg_m3,
        port_count,
        grain_length_m,
        initial_port_radius_m,
    )
    grain_outer_diameter_m = 2.0 * grain_outer_radius_m

    # -----------------------------------------------------------------
    # Injector first-pass sizing
    # -----------------------------------------------------------------
    injector_total_area_m2 = injector_total_area(
        mdot_ox_kg_s,
        injector_cd,
        oxidizer_liquid_density_kg_m3,
        injector_delta_p_pa,
    )
    injector_hole_diameter_m = equivalent_injector_hole_diameter(
        injector_total_area_m2,
        injector_hole_count,
    )

    # -----------------------------------------------------------------
    # Print results
    # -----------------------------------------------------------------
    print("=== Inputs ===")
    print(f"Thrust:                         {thrust_n:.3f} N")
    print(f"Burn time:                      {burn_time_s:.3f} s")
    print(f"O/F ratio:                      {of_ratio:.3f}")
    print(f"Isp:                            {isp_s:.3f} s")
    print(f"Pc:                             {chamber_pressure_pa/1e5:.3f} bar")
    print(f"c*:                             {cstar_mps:.3f} m/s")
    print()

    print("=== Blend ===")
    print(f"Fuel blend density:             {fuel_density_kg_m3:.3f} kg/m^3")
    print(f"ABS mass fraction:              {abs_mass_fraction:.5f}")
    print()

    print("=== Mass flow ===")
    print(f"Total mass flow:                {mdot_total_kg_s:.6f} kg/s")
    print(f"Oxidizer mass flow:             {mdot_ox_kg_s:.6f} kg/s")
    print(f"Fuel mass flow:                 {mdot_f_kg_s:.6f} kg/s")
    print()

    print("=== Required masses ===")
    print(f"Required oxidizer mass:         {m_ox_required_kg:.6f} kg")
    print(f"Loaded oxidizer mass:           {m_ox_loaded_kg:.6f} kg")
    print(f"Required fuel mass:             {m_f_required_kg:.6f} kg")
    print(f"Loaded fuel mass:               {m_f_loaded_kg:.6f} kg")
    print()

    print("=== Tank ===")
    print(f"Oxidizer liquid volume:         {oxidizer_liquid_volume_m3:.6f} m^3")
    print(f"Tank total volume:              {tank_volume_m3:.6f} m^3")
    print(f"Tank total volume:              {tank_volume_m3*1e3:.3f} L")
    print()

    print("=== Throat ===")
    print(f"Throat area:                    {throat_area_m2:.9f} m^2")
    print(f"Throat diameter:                {throat_diameter_m*1e3:.3f} mm")
    print()

    print("=== Grain ===")
    print(f"Initial total port area:        {total_port_area_m2:.9f} m^2")
    print(f"Initial port diameter:          {initial_port_diameter_m*1e3:.3f} mm")
    print(f"Initial regression rate:        {initial_rdot_m_s*1e3:.6f} mm/s")
    print(f"Grain length:                   {grain_length_m:.6f} m")
    print(f"Grain outer diameter:           {grain_outer_diameter_m*1e3:.3f} mm")
    print()

    print("=== Injector ===")
    print(f"Injector total area:            {injector_total_area_m2*1e6:.6f} mm^2")
    print(f"Injector hole diameter:         {injector_hole_diameter_m*1e3:.6f} mm")
'''

out = Path("/mnt/data/hybrid_first_pass_formulas.py")
out.write_text(script, encoding="utf-8")
print(f"Wrote {out}")
