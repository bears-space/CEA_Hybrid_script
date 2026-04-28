"""Approximate mass estimates for the first-pass structural components."""

from __future__ import annotations

import math
from typing import Mapping

from src.injector_design.injector_types import InjectorGeometryDefinition
from src.sizing.geometry_types import GeometryDefinition
from src.structural.structural_types import StructuralSizingResult


def _disc_mass_kg(diameter_m: float, thickness_m: float, density_kg_m3: float) -> float:
    return math.pi * (0.5 * float(diameter_m)) ** 2 * float(thickness_m) * float(density_kg_m3)


def _shell_mass_kg(inner_radius_m: float, thickness_m: float, length_m: float, density_kg_m3: float) -> float:
    outer_radius_m = inner_radius_m + float(thickness_m)
    return math.pi * (outer_radius_m**2 - inner_radius_m**2) * float(length_m) * float(density_kg_m3)


def estimate_structural_mass_breakdown(
    geometry: GeometryDefinition,
    injector_geometry: InjectorGeometryDefinition | None,
    result: StructuralSizingResult,
    materials: Mapping[str, object],
    structural_config: Mapping[str, object],
) -> dict[str, float]:
    """Estimate mass of the major pressure-containing structural components."""

    chamber_material = materials["chamber_wall"]
    forward_material = materials["forward_closure"]
    aft_material = materials["aft_closure"]
    injector_material = materials["injector_plate"]
    nozzle_material = materials["nozzle_mount"]
    fastener_material = materials["fasteners"]
    fastener_settings = dict(structural_config.get("fasteners", {}))

    shell_mass_kg = _shell_mass_kg(
        0.5 * float(geometry.chamber_id_m),
        result.chamber_wall_result.selected_thickness_m,
        float(geometry.total_chamber_length_m),
        chamber_material.density_kg_m3,
    )
    forward_mass_kg = _disc_mass_kg(
        result.forward_closure_result.loaded_diameter_m,
        result.forward_closure_result.selected_thickness_m,
        forward_material.density_kg_m3,
    )
    aft_mass_kg = _disc_mass_kg(
        result.aft_closure_result.loaded_diameter_m,
        result.aft_closure_result.selected_thickness_m,
        aft_material.density_kg_m3,
    )
    injector_diameter_m = (
        float(injector_geometry.plate_outer_diameter_m)
        if injector_geometry is not None
        else float(geometry.injector_face_diameter_m)
    )
    injector_mass_kg = _disc_mass_kg(
        injector_diameter_m,
        result.injector_plate_result.selected_thickness_m,
        injector_material.density_kg_m3,
    )
    nozzle_mount_mass_kg = _disc_mass_kg(
        result.nozzle_mount_result.loaded_diameter_m,
        result.nozzle_mount_result.selected_thickness_m,
        nozzle_material.density_kg_m3,
    )
    fastener_mass_kg = 0.0
    if result.fastener_result.fastener_count > 0 and result.fastener_result.nominal_diameter_m is not None:
        grip_length_m = float(fastener_settings["grip_length_m"])
        shank_area_m2 = math.pi * 0.25 * float(result.fastener_result.nominal_diameter_m) ** 2
        fastener_mass_kg = (
            float(result.fastener_result.fastener_count)
            * shank_area_m2
            * grip_length_m
            * fastener_material.density_kg_m3
            * 1.35
        )

    mass_breakdown = {
        "chamber_shell": float(shell_mass_kg),
        "forward_closure": float(forward_mass_kg),
        "aft_closure": float(aft_mass_kg),
        "injector_plate": float(injector_mass_kg),
        "nozzle_mount": float(nozzle_mount_mass_kg),
        "fasteners": float(fastener_mass_kg),
    }
    for key, value in list(mass_breakdown.items()):
        mass_breakdown[key] = float(value) * float(result.design_policy.mass_roundup_factor)
    return mass_breakdown
