"""Structured CEA result objects used by the workflow layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CEACaseInput:
    abs_volume_fraction: float
    fuel_temperature_k: float
    oxidizer_temperature_k: float
    of_ratio: float
    pc_bar: float
    ae_at: float


@dataclass(frozen=True)
class CEAPerformancePoint:
    case_input: CEACaseInput
    target_thrust_n: float
    cstar_mps: float
    isp_s: float
    isp_sl_s: float
    isp_vac_s: float
    cf: float
    cf_sea_level: float
    cf_vac: float
    gamma_e: float
    molecular_weight_exit: float
    chamber_temperature_k: float
    exit_pressure_bar: float
    exit_temperature_k: float
    throat_area_m2: float
    exit_area_m2: float
    thrust_sea_level_n: float
    thrust_vac_n: float
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CEASweepResult:
    config: dict[str, Any]
    cases: list[CEAPerformancePoint]
    failures: list[dict[str, Any]]
    total_combinations: int
    cpu_workers: int
    backend: str
    gpu_enabled: bool
