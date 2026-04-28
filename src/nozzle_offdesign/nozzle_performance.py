"""Reduced-order nozzle off-design operating-point evaluation."""

from __future__ import annotations

import math

from src.models.nozzle import evaluate_nozzle_performance
from src.nozzle_offdesign.expansion_state import classify_expansion_state
from src.nozzle_offdesign.nozzle_offdesign_types import NozzleOperatingPoint


def derive_exit_pressure_ratio(
    *,
    chamber_pressure_pa: float,
    exit_pressure_pa: float | None,
    fallback_ratio: float | None = None,
) -> float | None:
    """Return an exit-pressure ratio when the current operating point defines one."""

    if exit_pressure_pa is not None and chamber_pressure_pa > 0.0 and exit_pressure_pa >= 0.0:
        return float(exit_pressure_pa) / float(chamber_pressure_pa)
    return None if fallback_ratio is None else float(fallback_ratio)


def exit_mach_from_pressure_ratio(gamma: float | None, exit_pressure_ratio: float | None) -> float | None:
    """Approximate exit Mach from the isentropic pressure ratio when available."""

    if gamma is None or exit_pressure_ratio is None:
        return None
    if gamma <= 1.0 or exit_pressure_ratio <= 0.0 or exit_pressure_ratio >= 1.0:
        return None
    term = (1.0 / float(exit_pressure_ratio)) ** ((float(gamma) - 1.0) / float(gamma)) - 1.0
    if term < 0.0:
        return None
    return math.sqrt((2.0 / (float(gamma) - 1.0)) * term)


def evaluate_offdesign_operating_point(
    *,
    operating_point_label: str,
    time_s: float | None,
    chamber_pressure_pa: float,
    chamber_temp_k: float | None,
    gamma: float | None,
    molecular_weight: float | None,
    total_mass_flow_kg_s: float,
    throat_area_m2: float,
    exit_area_m2: float,
    ambient_pressure_pa: float,
    cf_vac: float,
    cstar_mps: float,
    exit_pressure_ratio: float | None,
    expansion_thresholds: dict[str, float],
    cf_penalty_multiplier: float = 1.0,
    notes: list[str] | None = None,
) -> NozzleOperatingPoint:
    """Evaluate one nozzle operating point under a selected ambient condition."""

    nozzle = evaluate_nozzle_performance(
        cstar_mps=float(cstar_mps),
        cf_vac=cf_vac,
        chamber_pressure_pa=chamber_pressure_pa,
        throat_area_m2=throat_area_m2,
        mdot_total_kg_s=total_mass_flow_kg_s,
        ambient_pressure_pa=ambient_pressure_pa,
        exit_area_m2=exit_area_m2,
        exit_pressure_ratio=exit_pressure_ratio,
        gamma_e=gamma,
        molecular_weight_exit=molecular_weight,
    )
    penalized_cf_actual = float(nozzle.cf_actual) * float(cf_penalty_multiplier)
    penalized_thrust_n = penalized_cf_actual * float(chamber_pressure_pa) * float(throat_area_m2)
    penalized_isp_s = 0.0 if total_mass_flow_kg_s <= 0.0 else penalized_thrust_n / (float(total_mass_flow_kg_s) * 9.80665)
    exit_pressure_pa = 0.0 if nozzle.exit_pressure_pa is None else float(nozzle.exit_pressure_pa)
    return NozzleOperatingPoint(
        operating_point_label=operating_point_label,
        time_s=time_s,
        chamber_pressure_pa=float(chamber_pressure_pa),
        chamber_temp_k=None if chamber_temp_k is None else float(chamber_temp_k),
        gamma=None if gamma is None else float(gamma),
        molecular_weight=None if molecular_weight is None else float(molecular_weight),
        total_mass_flow_kg_s=float(total_mass_flow_kg_s),
        throat_area_m2=float(throat_area_m2),
        exit_area_m2=float(exit_area_m2),
        area_ratio=float(exit_area_m2) / float(throat_area_m2),
        ambient_pressure_pa=float(ambient_pressure_pa),
        exit_pressure_pa=exit_pressure_pa,
        exit_mach=exit_mach_from_pressure_ratio(gamma, exit_pressure_ratio),
        cf_actual=penalized_cf_actual,
        thrust_n=penalized_thrust_n,
        isp_s=penalized_isp_s,
        expansion_state=classify_expansion_state(
            exit_pressure_pa=exit_pressure_pa,
            ambient_pressure_pa=ambient_pressure_pa,
            thresholds=expansion_thresholds,
        ),
        notes=list(notes or []),
    )
