"""Simple transient two-node wall model for first-pass engine thermal sizing."""

from __future__ import annotations

import math
from typing import Iterable


SIGMA_SB = 5.670374419e-8


def simulate_two_node_wall(
    *,
    time_s: Iterable[float],
    gas_temperature_k: Iterable[float],
    gas_side_htc_w_m2k: Iterable[float],
    wall_thickness_m: float,
    density_kg_m3: float,
    conductivity_w_mk: float,
    heat_capacity_j_kgk: float,
    outer_h_w_m2k: float,
    ambient_temp_k: float,
    initial_temp_k: float,
    emissivity: float,
    radiation_enabled: bool,
) -> dict[str, list[float] | float]:
    """Integrate a reduced-order two-node slab model per unit wall area."""

    time_values = [float(value) for value in time_s]
    gas_temp_values = [float(value) for value in gas_temperature_k]
    gas_htc_values = [float(value) for value in gas_side_htc_w_m2k]
    if not time_values:
        raise ValueError("Thermal wall model requires a non-empty time history.")
    if wall_thickness_m <= 0.0:
        raise ValueError("Wall thickness must be positive.")

    thickness = float(wall_thickness_m)
    mass_per_area_half = max(float(density_kg_m3) * thickness * 0.5, 1.0e-9)
    cp = max(float(heat_capacity_j_kgk), 1.0e-9)
    conduction_g_w_m2k = max(2.0 * float(conductivity_w_mk) / thickness, 1.0e-9)
    characteristic_length_m = thickness * 0.5

    inner_temp_k = float(initial_temp_k)
    outer_temp_k = float(initial_temp_k)
    inner_history = [inner_temp_k]
    outer_history = [outer_temp_k]
    heat_flux_history = [max(gas_htc_values[0] * (gas_temp_values[0] - inner_temp_k), 0.0)]
    biot_history = [gas_htc_values[0] * characteristic_length_m / max(float(conductivity_w_mk), 1.0e-9)]

    for index in range(1, len(time_values)):
        dt_s = max(time_values[index] - time_values[index - 1], 1.0e-9)
        gas_temp_k = gas_temp_values[index]
        gas_h = max(gas_htc_values[index], 1.0)
        q_gas_w_m2 = max(gas_h * (gas_temp_k - inner_temp_k), 0.0)
        q_cond_w_m2 = conduction_g_w_m2k * (inner_temp_k - outer_temp_k)
        q_outer_w_m2 = float(outer_h_w_m2k) * max(outer_temp_k - ambient_temp_k, 0.0)
        if radiation_enabled:
            q_outer_w_m2 += float(emissivity) * SIGMA_SB * max(outer_temp_k**4 - ambient_temp_k**4, 0.0)

        inner_temp_k += (q_gas_w_m2 - q_cond_w_m2) * dt_s / (mass_per_area_half * cp)
        outer_temp_k += (q_cond_w_m2 - q_outer_w_m2) * dt_s / (mass_per_area_half * cp)

        inner_history.append(inner_temp_k)
        outer_history.append(outer_temp_k)
        heat_flux_history.append(q_gas_w_m2)
        biot_history.append(gas_h * characteristic_length_m / max(float(conductivity_w_mk), 1.0e-9))

    return {
        "time_s": time_values,
        "inner_wall_temp_k": inner_history,
        "outer_wall_temp_k": outer_history,
        "heat_flux_w_m2": heat_flux_history,
        "peak_biot_number": max(biot_history),
    }


def round_up_thickness(required_thickness_m: float, increment_m: float, minimum_thickness_m: float) -> float:
    """Round up a protection thickness with an explicit manufacturing increment."""

    base = max(float(required_thickness_m), float(minimum_thickness_m), 0.0)
    if base <= 0.0:
        return 0.0
    increment = max(float(increment_m), 1.0e-9)
    return math.ceil(base / increment) * increment
