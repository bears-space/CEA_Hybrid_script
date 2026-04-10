"""Nozzle performance helpers shared by sizing and transient simulation."""

from __future__ import annotations

from dataclasses import dataclass
import math

from blowdown_hybrid.constants import G0_MPS2


STANDARD_SEA_LEVEL_PRESSURE_PA = 101325.0


@dataclass(frozen=True)
class NozzlePerformance:
    cstar_mps: float
    cf_vac: float
    cf_actual: float
    thrust_vac_n: float
    thrust_actual_n: float
    isp_vac_s: float
    isp_actual_s: float
    exit_pressure_pa: float | None = None
    gamma_e: float | None = None
    molecular_weight_exit: float | None = None


def area_ratio(exit_area_m2: float, throat_area_m2: float) -> float:
    if throat_area_m2 <= 0.0:
        raise ValueError("Throat area must be positive.")
    return float(exit_area_m2) / float(throat_area_m2)


def thrust_from_cf_pc_at(cf: float, chamber_pressure_pa: float, throat_area_m2: float) -> float:
    return float(cf) * float(chamber_pressure_pa) * float(throat_area_m2)


def cf_from_thrust(thrust_n: float, chamber_pressure_pa: float, throat_area_m2: float) -> float:
    denominator = float(chamber_pressure_pa) * float(throat_area_m2)
    if denominator <= 0.0:
        raise ValueError("Chamber pressure and throat area must be positive.")
    return float(thrust_n) / denominator


def isp_from_thrust(thrust_n: float, mdot_total_kg_s: float) -> float:
    if mdot_total_kg_s <= 0.0:
        return 0.0
    return float(thrust_n) / (float(mdot_total_kg_s) * G0_MPS2)


def cf_vac_from_isp_and_cstar(isp_vac_s: float, cstar_mps: float) -> float:
    if cstar_mps <= 0.0:
        raise ValueError("c* must be positive.")
    return float(isp_vac_s) * G0_MPS2 / float(cstar_mps)


def cf_actual_from_cf_vac(cf_vac: float, chamber_pressure_pa: float, ambient_pressure_pa: float, area_ratio_value: float) -> float:
    if chamber_pressure_pa <= 0.0:
        return 0.0
    return float(cf_vac) - (float(ambient_pressure_pa) / float(chamber_pressure_pa)) * float(area_ratio_value)


def exit_pressure_from_ratio(chamber_pressure_pa: float, exit_pressure_ratio: float | None) -> float | None:
    if exit_pressure_ratio is None:
        return None
    return float(chamber_pressure_pa) * float(exit_pressure_ratio)


def evaluate_nozzle_performance(
    cstar_mps: float,
    cf_vac: float,
    chamber_pressure_pa: float,
    throat_area_m2: float,
    mdot_total_kg_s: float,
    ambient_pressure_pa: float,
    exit_area_m2: float,
    *,
    exit_pressure_ratio: float | None = None,
    gamma_e: float | None = None,
    molecular_weight_exit: float | None = None,
) -> NozzlePerformance:
    ae_at = area_ratio(exit_area_m2, throat_area_m2)
    cf_actual = cf_actual_from_cf_vac(cf_vac, chamber_pressure_pa, ambient_pressure_pa, ae_at)
    thrust_vac_n = thrust_from_cf_pc_at(cf_vac, chamber_pressure_pa, throat_area_m2)
    thrust_actual_n = thrust_from_cf_pc_at(cf_actual, chamber_pressure_pa, throat_area_m2)
    return NozzlePerformance(
        cstar_mps=float(cstar_mps),
        cf_vac=float(cf_vac),
        cf_actual=float(cf_actual),
        thrust_vac_n=thrust_vac_n,
        thrust_actual_n=thrust_actual_n,
        isp_vac_s=isp_from_thrust(thrust_vac_n, mdot_total_kg_s),
        isp_actual_s=isp_from_thrust(thrust_actual_n, mdot_total_kg_s),
        exit_pressure_pa=exit_pressure_from_ratio(chamber_pressure_pa, exit_pressure_ratio),
        gamma_e=None if gamma_e is None else float(gamma_e),
        molecular_weight_exit=None if molecular_weight_exit is None else float(molecular_weight_exit),
    )


def diameter_from_area(area_m2: float) -> float:
    if area_m2 <= 0.0:
        raise ValueError("Area must be positive.")
    return math.sqrt(4.0 * float(area_m2) / math.pi)

