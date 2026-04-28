"""Simple ambient-pressure profile helpers for launch-environment checks."""

from __future__ import annotations

import math


STANDARD_SEA_LEVEL_PRESSURE_PA = 101325.0
STANDARD_SEA_LEVEL_TEMPERATURE_K = 288.15
SCALE_HEIGHT_M = 8434.5


def pressure_from_altitude_m(altitude_m: float) -> float:
    """Return a simple exponential-atmosphere pressure approximation."""

    altitude = max(float(altitude_m), 0.0)
    return STANDARD_SEA_LEVEL_PRESSURE_PA * math.exp(-altitude / SCALE_HEIGHT_M)


def altitude_from_pressure_pa(ambient_pressure_pa: float) -> float | None:
    """Invert the simple exponential atmosphere to approximate altitude."""

    pressure = float(ambient_pressure_pa)
    if pressure <= 0.0:
        return None
    return -SCALE_HEIGHT_M * math.log(pressure / STANDARD_SEA_LEVEL_PRESSURE_PA)


def temperature_from_altitude_m(altitude_m: float) -> float:
    """Return a simple ISA-like temperature placeholder."""

    altitude = max(float(altitude_m), 0.0)
    lapse_rate_k_m = 0.0065
    tropopause_altitude_m = 11000.0
    if altitude <= tropopause_altitude_m:
        return STANDARD_SEA_LEVEL_TEMPERATURE_K - lapse_rate_k_m * altitude
    return STANDARD_SEA_LEVEL_TEMPERATURE_K - lapse_rate_k_m * tropopause_altitude_m
