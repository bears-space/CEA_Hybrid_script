"""Axially resolved port marching helpers for the Step 3 quasi-1D solver."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from blowdown_hybrid.models import GrainConfig

from src.models.regression import PowerLawRegressionModel, fuel_addition_rate_kg_s as cell_fuel_addition_rate_kg_s
from src.simulation.axial_mesh import AxialMesh
from src.sizing.geometry_rules import area_from_diameter
from src.sizing.geometry_types import GeometryDefinition


@dataclass(frozen=True)
class AxialMarchResult:
    port_area_m2: np.ndarray
    wetted_perimeter_m: np.ndarray
    oxidizer_mass_flow_kg_s: np.ndarray
    oxidizer_flux_kg_m2_s: np.ndarray
    effective_regression_flux_kg_m2_s: np.ndarray
    regression_rate_m_s: np.ndarray
    fuel_addition_rate_kg_s: np.ndarray
    fuel_addition_rate_kg_s_m: np.ndarray
    cumulative_fuel_mass_flow_kg_s: np.ndarray
    total_mass_flow_kg_s: np.ndarray
    local_of_ratio: np.ndarray
    total_fuel_mass_flow_kg_s: float
    exit_total_mass_flow_kg_s: float
    free_volume_m3: float
    lstar_m: float


def axial_correction_profile(mesh: AxialMesh, mode: str, strength: float, decay_fraction: float) -> np.ndarray:
    if mode == "uniform":
        return np.ones(mesh.cell_count, dtype=float)

    length_scale_m = max(mesh.grain_length_m * float(decay_fraction), 1.0e-9)
    raw = 1.0 + float(strength) * np.exp(-mesh.cell_centers_m / length_scale_m)
    return raw / np.mean(raw)


def current_free_volume_m3(geometry: GeometryDefinition, mesh: AxialMesh, port_area_m2: np.ndarray) -> float:
    prechamber_volume_m3 = area_from_diameter(geometry.chamber_id_m) * geometry.prechamber_length_m
    postchamber_volume_m3 = area_from_diameter(geometry.chamber_id_m) * geometry.postchamber_length_m
    return float(prechamber_volume_m3 + postchamber_volume_m3 + np.sum(port_area_m2 * mesh.cell_lengths_m))


def march_port_ballistics(
    *,
    mdot_ox_kg_s: float,
    port_radii_m: np.ndarray,
    geometry: GeometryDefinition,
    mesh: AxialMesh,
    grain_cfg: GrainConfig,
    regression_model: PowerLawRegressionModel,
    axial_correction_mode: str,
    axial_head_end_bias_strength: float,
    axial_bias_decay_fraction: float,
) -> AxialMarchResult:
    """
    March oxidizer flow through the grain and add fuel cell-by-cell.

    Simplifying approximation:
    oxidizer mass flow is treated as conserved along the port at this stage, while fuel
    is added axially from local regression. This keeps the model auditable and fast while
    still resolving axial growth, downstream total-flow increase, and local O/F variation.
    """

    if np.any(port_radii_m <= 0.0):
        raise ValueError("All port radii must remain positive in the 1D solver.")

    correction_profile = axial_correction_profile(
        mesh,
        mode=axial_correction_mode,
        strength=axial_head_end_bias_strength,
        decay_fraction=axial_bias_decay_fraction,
    )
    port_area_m2 = grain_cfg.port_count * math.pi * np.square(port_radii_m)
    wetted_perimeter_m = grain_cfg.port_count * 2.0 * math.pi * port_radii_m
    if np.any(port_area_m2 <= 0.0):
        raise ValueError("Local port area became non-physical in the 1D solver.")

    oxidizer_mass_flow_kg_s = np.full(mesh.cell_count, float(mdot_ox_kg_s), dtype=float)
    oxidizer_flux_kg_m2_s = oxidizer_mass_flow_kg_s / port_area_m2
    effective_regression_flux_kg_m2_s = oxidizer_flux_kg_m2_s * correction_profile
    regression_rate_m_s = np.array(
        [regression_model.rate_m_s(gox, factor) for gox, factor in zip(oxidizer_flux_kg_m2_s, correction_profile)],
        dtype=float,
    )
    fuel_addition_rate_kg_s = np.array(
        [
            cell_fuel_addition_rate_kg_s(
                fuel_density_kg_m3=grain_cfg.fuel_density_kg_m3,
                port_radius_m=float(radius),
                cell_length_m=float(dx),
                port_count=grain_cfg.port_count,
                regression_rate_m_s=float(rdot),
            )
            for radius, dx, rdot in zip(port_radii_m, mesh.cell_lengths_m, regression_rate_m_s)
        ],
        dtype=float,
    )
    fuel_addition_rate_kg_s_m = fuel_addition_rate_kg_s / mesh.cell_lengths_m
    cumulative_fuel_mass_flow_kg_s = np.cumsum(fuel_addition_rate_kg_s)
    total_mass_flow_kg_s = float(mdot_ox_kg_s) + cumulative_fuel_mass_flow_kg_s
    local_of_ratio = np.divide(
        float(mdot_ox_kg_s),
        np.maximum(cumulative_fuel_mass_flow_kg_s, 1.0e-12),
    )
    free_volume_m3 = current_free_volume_m3(geometry, mesh, port_area_m2)
    lstar_m = free_volume_m3 / geometry.throat_area_m2

    return AxialMarchResult(
        port_area_m2=port_area_m2,
        wetted_perimeter_m=wetted_perimeter_m,
        oxidizer_mass_flow_kg_s=oxidizer_mass_flow_kg_s,
        oxidizer_flux_kg_m2_s=oxidizer_flux_kg_m2_s,
        effective_regression_flux_kg_m2_s=effective_regression_flux_kg_m2_s,
        regression_rate_m_s=regression_rate_m_s,
        fuel_addition_rate_kg_s=fuel_addition_rate_kg_s,
        fuel_addition_rate_kg_s_m=fuel_addition_rate_kg_s_m,
        cumulative_fuel_mass_flow_kg_s=cumulative_fuel_mass_flow_kg_s,
        total_mass_flow_kg_s=total_mass_flow_kg_s,
        local_of_ratio=local_of_ratio,
        total_fuel_mass_flow_kg_s=float(cumulative_fuel_mass_flow_kg_s[-1]),
        exit_total_mass_flow_kg_s=float(total_mass_flow_kg_s[-1]),
        free_volume_m3=free_volume_m3,
        lstar_m=lstar_m,
    )
