"""Thermodynamic helpers for the self-pressurized N2O tank model."""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from blowdown_hybrid.constants import N2O_T_MAX_K, N2O_T_MIN_K, NITROUS_OXIDE_FLUID
from blowdown_hybrid.models import TankConfig, TankThermoState

try:
    import CoolProp.CoolProp as CP
except ImportError:
    CP = None


def _require_coolprop():
    if CP is None:
        raise RuntimeError("CoolProp is required for the blowdown model. Install it in the project environment.")


def validate_n2o_temperature_k(T_k: float) -> float:
    """Validate that the requested N2O saturation temperature is in the supported range."""
    if not N2O_T_MIN_K <= T_k <= N2O_T_MAX_K:
        raise ValueError(
            f"Oxidizer temperature must stay within the supported N2O saturation range of "
            f"{N2O_T_MIN_K:.1f} K to {N2O_T_MAX_K:.1f} K."
        )
    return T_k


@lru_cache(maxsize=2048)
def _sat_props_tuple_n2o(T_k: float) -> tuple[float, float, float, float, float, float]:
    """Cached saturated N2O properties keyed by temperature."""
    _require_coolprop()
    validate_n2o_temperature_k(T_k)
    p_pa = CP.PropsSI("P", "T", T_k, "Q", 0, NITROUS_OXIDE_FLUID)
    rho_l = CP.PropsSI("Dmass", "T", T_k, "Q", 0, NITROUS_OXIDE_FLUID)
    rho_v = CP.PropsSI("Dmass", "T", T_k, "Q", 1, NITROUS_OXIDE_FLUID)
    u_l = CP.PropsSI("Umass", "T", T_k, "Q", 0, NITROUS_OXIDE_FLUID)
    u_v = CP.PropsSI("Umass", "T", T_k, "Q", 1, NITROUS_OXIDE_FLUID)
    h_l = CP.PropsSI("Hmass", "T", T_k, "Q", 0, NITROUS_OXIDE_FLUID)
    return p_pa, rho_l, rho_v, u_l, u_v, h_l


def sat_props_n2o(T_k: float) -> TankThermoState:
    """Saturated liquid and vapor properties for N2O at the given temperature."""
    p_pa, rho_l, rho_v, u_l, u_v, h_l = _sat_props_tuple_n2o(float(T_k))
    return TankThermoState(
        T_k=T_k,
        p_pa=p_pa,
        quality=np.nan,
        rho_l_kg_m3=rho_l,
        rho_v_kg_m3=rho_v,
        u_l_j_kg=u_l,
        u_v_j_kg=u_v,
        h_l_j_kg=h_l,
    )


def initial_tank_state_from_temperature(oxidizer_temp_k: float) -> TankThermoState:
    """Return the saturated initial tank state for a self-pressurized N2O tank at the chosen temperature."""
    return sat_props_n2o(oxidizer_temp_k)


def quality_from_T_m_V(T_k: float, mass_kg: float, volume_m3: float) -> float:
    """Compute equilibrium vapor mass fraction from T, total mass, and total volume."""
    props = sat_props_n2o(T_k)
    v_total = volume_m3 / mass_kg
    v_l = 1.0 / props.rho_l_kg_m3
    v_v = 1.0 / props.rho_v_kg_m3
    return (v_total - v_l) / (v_v - v_l)


def tank_internal_energy_from_T_x(T_k: float, quality: float, mass_kg: float) -> float:
    """Total tank internal energy for a saturated mixture."""
    props = sat_props_n2o(T_k)
    u_mix = (1.0 - quality) * props.u_l_j_kg + quality * props.u_v_j_kg
    return mass_kg * u_mix


def initial_tank_state_from_mass_and_temperature(tank: TankConfig) -> tuple[TankThermoState, float]:
    """
    Build an initial two-phase saturated tank state from fixed volume, mass, and temperature.
    """
    quality = quality_from_T_m_V(tank.initial_temp_k, tank.initial_mass_kg, tank.volume_m3)
    if not 0.0 <= quality <= 1.0:
        raise ValueError(
            "Initial tank state is not a saturated two-phase state. "
            "Adjust tank volume, initial mass, or initial temperature."
        )
    props = sat_props_n2o(tank.initial_temp_k)
    props.quality = quality
    total_u = tank_internal_energy_from_T_x(tank.initial_temp_k, quality, tank.initial_mass_kg)
    return props, total_u


def tank_state_from_mass_energy_volume(
    mass_kg: float,
    total_internal_energy_j: float,
    volume_m3: float,
) -> TankThermoState:
    """
    Recover the saturated tank state from total mass, total internal energy, and total volume.
    """
    if mass_kg <= 0.0:
        raise ValueError("Tank mass must remain positive.")

    target_u_j_kg = total_internal_energy_j / mass_kg
    temperatures = np.linspace(N2O_T_MIN_K, N2O_T_MAX_K, 600)
    valid_temperatures = []
    valid_residuals = []

    for temperature in temperatures:
        quality = quality_from_T_m_V(temperature, mass_kg, volume_m3)
        if 0.0 <= quality <= 1.0:
            props = sat_props_n2o(temperature)
            u_mix = (1.0 - quality) * props.u_l_j_kg + quality * props.u_v_j_kg
            valid_temperatures.append(temperature)
            valid_residuals.append(u_mix - target_u_j_kg)

    if len(valid_temperatures) < 2:
        raise RuntimeError(
            "Could not find a valid saturated two-phase tank state. "
            "The tank may have become single-phase or the inputs are inconsistent."
        )

    bracket = None
    for index in range(len(valid_temperatures) - 1):
        left_residual = valid_residuals[index]
        right_residual = valid_residuals[index + 1]
        if left_residual == 0.0:
            bracket = (valid_temperatures[index], valid_temperatures[index])
            break
        if left_residual * right_residual < 0.0:
            bracket = (valid_temperatures[index], valid_temperatures[index + 1])
            break

    if bracket is None:
        nearest_index = int(np.argmin(np.abs(valid_residuals)))
        if abs(valid_residuals[nearest_index]) > 1e-3:
            raise RuntimeError("Failed to bracket the tank-state solve in temperature.")
        temperature_star = valid_temperatures[nearest_index]
        quality_star = quality_from_T_m_V(temperature_star, mass_kg, volume_m3)
        props = sat_props_n2o(temperature_star)
        props.quality = quality_star
        return props

    temperature_low, temperature_high = bracket
    if temperature_low != temperature_high:
        for _ in range(100):
            temperature_mid = 0.5 * (temperature_low + temperature_high)
            quality_low = quality_from_T_m_V(temperature_low, mass_kg, volume_m3)
            quality_mid = quality_from_T_m_V(temperature_mid, mass_kg, volume_m3)
            props_low = sat_props_n2o(temperature_low)
            props_mid = sat_props_n2o(temperature_mid)
            residual_low = (
                (1.0 - quality_low) * props_low.u_l_j_kg + quality_low * props_low.u_v_j_kg - target_u_j_kg
            )
            residual_mid = (
                (1.0 - quality_mid) * props_mid.u_l_j_kg + quality_mid * props_mid.u_v_j_kg - target_u_j_kg
            )
            if abs(residual_mid) < 1e-7:
                temperature_low = temperature_high = temperature_mid
                break
            if residual_low * residual_mid <= 0.0:
                temperature_high = temperature_mid
            else:
                temperature_low = temperature_mid

    temperature_star = 0.5 * (temperature_low + temperature_high)
    quality_star = quality_from_T_m_V(temperature_star, mass_kg, volume_m3)
    props = sat_props_n2o(temperature_star)
    props.quality = quality_star
    return props
