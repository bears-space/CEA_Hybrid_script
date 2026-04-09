"""Minimal chamber closure helpers used by the modular 0D workflow."""

from __future__ import annotations


def chamber_pressure_from_cstar(mdot_total_kg_s: float, throat_area_m2: float, cstar_mps: float) -> float:
    if throat_area_m2 <= 0.0 or cstar_mps <= 0.0:
        raise ValueError("Throat area and c* must be positive.")
    return float(mdot_total_kg_s) * float(cstar_mps) / float(throat_area_m2)
