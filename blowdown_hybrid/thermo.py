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


class TankStateLimitReached(RuntimeError):
    """Raised when the rigid-tank state leaves the supported saturated two-phase model."""

    def __init__(self, message: str, *, boundary_state: TankThermoState | None = None):
        super().__init__(message)
        self.boundary_state = boundary_state


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
    temperature_hint_k: float | None = None,
) -> TankThermoState:
    """
    Recover the saturated tank state from total mass, total internal energy, and total volume.
    """
    if mass_kg <= 0.0:
        raise ValueError("Tank mass must remain positive.")

    target_u_j_kg = total_internal_energy_j / mass_kg

    def residual_at_temperature(temperature_k: float) -> tuple[float, float, TankThermoState] | None:
        quality = quality_from_T_m_V(temperature_k, mass_kg, volume_m3)
        if not 0.0 <= quality <= 1.0:
            return None
        props = sat_props_n2o(temperature_k)
        u_mix = (1.0 - quality) * props.u_l_j_kg + quality * props.u_v_j_kg
        return u_mix - target_u_j_kg, quality, props

    def solve_bracketed(temperature_low: float, temperature_high: float) -> TankThermoState:
        left = residual_at_temperature(temperature_low)
        right = residual_at_temperature(temperature_high)
        if left is None or right is None:
            raise RuntimeError("Attempted to solve a tank-state bracket outside the valid two-phase region.")
        residual_low = left[0]
        residual_high = right[0]
        if abs(residual_low) < 1e-7:
            props = left[2]
            props.quality = left[1]
            return props
        if abs(residual_high) < 1e-7:
            props = right[2]
            props.quality = right[1]
            return props

        for _ in range(80):
            temperature_mid = 0.5 * (temperature_low + temperature_high)
            middle = residual_at_temperature(temperature_mid)
            if middle is None:
                break
            residual_mid = middle[0]
            if abs(residual_mid) < 1e-7:
                props = middle[2]
                props.quality = middle[1]
                return props
            if residual_low * residual_mid <= 0.0:
                temperature_high = temperature_mid
                residual_high = residual_mid
            else:
                temperature_low = temperature_mid
                residual_low = residual_mid

        temperature_star = 0.5 * (temperature_low + temperature_high)
        solved = residual_at_temperature(temperature_star)
        if solved is None:
            raise RuntimeError("Failed to recover a valid two-phase tank state from the bracketed solve.")
        props = solved[2]
        props.quality = solved[1]
        return props

    def raise_two_phase_limit(message: str, *, nearest_index: int | None = None) -> None:
        boundary_state = None
        if nearest_index is not None and 0 <= nearest_index < len(valid_temperatures):
            solved = residual_at_temperature(valid_temperatures[nearest_index])
            if solved is not None:
                boundary_state = solved[2]
                boundary_state.quality = solved[1]
        raise TankStateLimitReached(message, boundary_state=boundary_state)

    if temperature_hint_k is not None:
        hint = min(max(float(temperature_hint_k), N2O_T_MIN_K), N2O_T_MAX_K)
        center = residual_at_temperature(hint)
        if center is not None:
            if abs(center[0]) < 1e-7:
                props = center[2]
                props.quality = center[1]
                return props

            span_k = 0.25
            for _ in range(14):
                left_temperature = max(N2O_T_MIN_K, hint - span_k)
                right_temperature = min(N2O_T_MAX_K, hint + span_k)
                left = residual_at_temperature(left_temperature)
                right = residual_at_temperature(right_temperature)

                if left is not None and right is not None:
                    if left[0] == 0.0:
                        props = left[2]
                        props.quality = left[1]
                        return props
                    if right[0] == 0.0:
                        props = right[2]
                        props.quality = right[1]
                        return props
                    if left[0] * right[0] < 0.0:
                        return solve_bracketed(left_temperature, right_temperature)

                if left_temperature <= N2O_T_MIN_K and right_temperature >= N2O_T_MAX_K:
                    break
                span_k *= 2.0

    # This fallback should be rare; keep it coarse and let the bracketed solve recover precision.
    temperatures = np.linspace(N2O_T_MIN_K, N2O_T_MAX_K, 96)
    valid_temperatures = []
    valid_residuals = []

    for temperature in temperatures:
        solved = residual_at_temperature(float(temperature))
        if solved is not None:
            valid_temperatures.append(float(temperature))
            valid_residuals.append(solved[0])

    if len(valid_temperatures) < 2:
        raise TankStateLimitReached(
            "The tank left the supported saturated two-phase N2O model. "
            "The state likely became single-phase or thermodynamically inconsistent."
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
            quality_hint = None
            solved = residual_at_temperature(valid_temperatures[nearest_index])
            if solved is not None:
                quality_hint = solved[1]
            quality_suffix = "" if quality_hint is None else f" near vapor quality {quality_hint:.3f}"
            raise_two_phase_limit(
                "The tank left the supported saturated two-phase N2O model"
                f"{quality_suffix}.",
                nearest_index=nearest_index,
            )
        temperature_star = valid_temperatures[nearest_index]
        solved = residual_at_temperature(temperature_star)
        assert solved is not None
        props = solved[2]
        props.quality = solved[1]
        return props

    temperature_low, temperature_high = bracket
    return solve_bracketed(temperature_low, temperature_high)
