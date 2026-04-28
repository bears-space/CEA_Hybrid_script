"""Reduced-order gas-side heat-transfer correlations for engine regions."""

from __future__ import annotations

import math
from typing import Iterable


REGION_HTC_FACTORS = {
    "prechamber": 0.58,
    "chamber": 0.68,
    "postchamber": 0.74,
    "throat": 1.55,
    "diverging_nozzle": 0.62,
    "injector_face": 0.78,
}


def effective_gas_temperature_k(region_name: str, chamber_temperature_k: float, *, area_ratio: float = 1.0) -> float:
    """Return a region-wise effective gas temperature placeholder."""

    factors = {
        "prechamber": 0.98,
        "chamber": 1.0,
        "postchamber": 0.97,
        "throat": 0.93,
        "diverging_nozzle": max(0.72, 0.9 / math.sqrt(max(area_ratio, 1.0))),
        "injector_face": 0.95,
    }
    return float(chamber_temperature_k) * float(factors.get(region_name, 1.0))


def estimate_region_gas_side_htc_w_m2k(
    *,
    region_name: str,
    chamber_pressure_pa: float,
    cstar_mps: float,
    throat_diameter_m: float,
    area_ratio: float,
    gamma: float,
    throat_multiplier: float,
    injector_face_multiplier: float,
) -> float:
    """Estimate gas-side HTC with a clearly labeled Bartz-like placeholder correlation."""

    pc_mpa = max(float(chamber_pressure_pa), 1.0e3) / 1.0e6
    cstar_term = max(float(cstar_mps), 400.0)
    throat_diameter_term = max(float(throat_diameter_m), 1.0e-4)
    gamma_term = max(float(gamma), 1.01)

    base_h = (
        2400.0
        * (pc_mpa / 3.0) ** 0.8
        * (1500.0 / cstar_term) ** 0.2
        * (0.03 / throat_diameter_term) ** 0.2
        * (gamma_term / 1.2) ** 0.5
    )
    factor = float(REGION_HTC_FACTORS.get(region_name, 1.0))
    if region_name == "throat":
        factor *= float(throat_multiplier)
    if region_name == "injector_face":
        factor *= float(injector_face_multiplier)
    if region_name == "diverging_nozzle":
        factor /= max(math.sqrt(max(float(area_ratio), 1.0)), 1.0)
    return max(base_h * factor, 10.0)


def estimate_region_htc_history_w_m2k(
    *,
    region_name: str,
    chamber_pressure_pa_time: Iterable[float],
    cstar_time: Iterable[float],
    throat_diameter_m: float,
    area_ratio: float,
    gamma_time: Iterable[float],
    throat_multiplier: float,
    injector_face_multiplier: float,
) -> list[float]:
    """Return a time history of gas-side HTCs for a named engine region."""

    return [
        estimate_region_gas_side_htc_w_m2k(
            region_name=region_name,
            chamber_pressure_pa=pc_pa,
            cstar_mps=cstar_mps,
            throat_diameter_m=throat_diameter_m,
            area_ratio=area_ratio,
            gamma=gamma,
            throat_multiplier=throat_multiplier,
            injector_face_multiplier=injector_face_multiplier,
        )
        for pc_pa, cstar_mps, gamma in zip(chamber_pressure_pa_time, cstar_time, gamma_time)
    ]
