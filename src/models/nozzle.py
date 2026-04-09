"""Nozzle performance helpers for the modular workflow."""

from __future__ import annotations


def thrust_from_cf_pc_at(cf: float, chamber_pressure_pa: float, throat_area_m2: float) -> float:
    return float(cf) * float(chamber_pressure_pa) * float(throat_area_m2)
