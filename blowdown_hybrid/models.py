"""Dataclasses used by the blowdown model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TankConfig:
    volume_m3: float
    initial_mass_kg: float
    initial_temp_k: float


@dataclass(frozen=True)
class FeedConfig:
    line_id_m: float
    line_length_m: float
    friction_factor: float
    minor_loss_k_total: float


@dataclass(frozen=True)
class InjectorConfig:
    cd: float
    total_area_m2: float
    hole_count: int


@dataclass(frozen=True)
class GrainConfig:
    fuel_density_kg_m3: float
    a_reg_si: float
    n_reg: float
    port_count: int
    initial_port_radius_m: float
    grain_length_m: float
    outer_radius_m: Optional[float] = None


@dataclass(frozen=True)
class NozzleConfig:
    throat_area_m2: float
    exit_area_m2: float
    cstar_mps: float
    cf: float


@dataclass(frozen=True)
class SimulationConfig:
    dt_s: float
    burn_time_s: float
    ambient_pressure_pa: float = 101325.0
    max_inner_iterations: int = 80
    relaxation: float = 0.35
    relative_tolerance: float = 1e-6
    stop_when_tank_quality_exceeds: float = 0.95


@dataclass(frozen=True)
class DesignPoint:
    mdot_total_kg_s: float
    of_ratio: float
    chamber_pressure_pa: float


@dataclass
class TankThermoState:
    T_k: float
    p_pa: float
    quality: float
    rho_l_kg_m3: float
    rho_v_kg_m3: float
    u_l_j_kg: float
    u_v_j_kg: float
    h_l_j_kg: float


@dataclass(frozen=True)
class State:
    time_s: float
    tank_mass_kg: float
    tank_internal_energy_j: float
    port_radius_m: float
