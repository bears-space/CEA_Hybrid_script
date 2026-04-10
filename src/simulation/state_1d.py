"""Dataclasses for the quasi-1D internal ballistics solver state."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Ballistics1DSettings:
    solver_mode: str
    axial_cell_count: int
    time_step_s: float
    max_simulation_time_s: float
    ambient_pressure_pa: float
    prechamber_model_mode: str
    postchamber_model_mode: str
    performance_lookup_mode: str
    regression_model_mode: str
    geometry_input_source: str
    geometry_path: str
    auto_freeze_geometry_if_missing: bool
    record_every_n_steps: int
    station_sample_count: int
    compare_to_0d: bool
    axial_correction_mode: str
    axial_head_end_bias_strength: float
    axial_bias_decay_fraction: float
    max_port_growth_fraction_per_step: float
    max_pressure_iterations: int
    pressure_relaxation: float
    pressure_relative_tolerance: float


@dataclass
class Ballistics1DState:
    time_s: float
    tank_mass_kg: float
    tank_internal_energy_j: float
    port_radii_m: np.ndarray
