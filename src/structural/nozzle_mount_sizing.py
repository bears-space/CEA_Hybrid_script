"""Simplified aft-interface and nozzle-retention sizing placeholders."""

from __future__ import annotations

from typing import Any, Mapping

from src.sizing.geometry_types import GeometryDefinition
from src.structural.closure_sizing import circular_plate_bending_stress_pa, required_circular_plate_thickness_m
from src.structural.pressure_vessel import round_up_to_increment
from src.structural.structural_types import MaterialDefinition, NozzleMountSizingResult, StructuralDesignPolicy, StructuralLoadCase


def size_nozzle_mount(
    structural_config: Mapping[str, Any],
    geometry: GeometryDefinition,
    load_case: StructuralLoadCase,
    material: MaterialDefinition,
    policy: StructuralDesignPolicy,
) -> NozzleMountSizingResult:
    """Run a conservative nozzle-mount thickness placeholder check."""

    settings = dict(structural_config.get("nozzle_mount", {}))
    warnings: list[str] = []
    loaded_diameter_m = settings.get("loaded_diameter_m")
    if loaded_diameter_m is None:
        loaded_diameter_m = float(geometry.throat_diameter_m) * float(settings["loaded_diameter_scale"])
    pressure_pa = max(float(load_case.chamber_pressure_pa) - float(load_case.ambient_pressure_pa), 0.0)
    required_thickness_m = required_circular_plate_thickness_m(
        pressure_pa,
        float(loaded_diameter_m),
        float(material.allowable_stress_pa),
        model_type=policy.nozzle_mount_model_type,
        poisson_ratio=material.poisson_ratio,
    )
    selected_thickness_m = round_up_to_increment(
        max(
            required_thickness_m + float(policy.corrosion_or_manufacturing_allowance_m),
            float(settings.get("minimum_thickness_m") or policy.minimum_flange_thickness_m),
        ),
        float(policy.thickness_roundup_increment_m),
    )
    estimated_bending_stress_pa = circular_plate_bending_stress_pa(
        pressure_pa,
        float(loaded_diameter_m),
        selected_thickness_m,
        model_type=policy.nozzle_mount_model_type,
        poisson_ratio=material.poisson_ratio,
    )
    margin_to_allowable = float(material.allowable_stress_pa) / max(estimated_bending_stress_pa, 1.0e-12) - 1.0
    if float(loaded_diameter_m) < float(geometry.throat_diameter_m):
        warnings.append("Nozzle-mount loaded diameter is smaller than the throat diameter, which is not physically credible.")
    return NozzleMountSizingResult(
        material_name=material.material_name,
        allowable_stress_pa=float(material.allowable_stress_pa),
        chamber_pressure_pa=float(load_case.chamber_pressure_pa),
        loaded_diameter_m=float(loaded_diameter_m),
        nozzle_separating_force_n=float(load_case.nozzle_separating_force_n),
        required_thickness_m=float(required_thickness_m),
        selected_thickness_m=float(selected_thickness_m),
        estimated_bending_stress_pa=float(estimated_bending_stress_pa),
        margin_to_allowable=float(margin_to_allowable),
        model_type=policy.nozzle_mount_model_type,
        valid=bool(selected_thickness_m >= required_thickness_m and margin_to_allowable >= 0.0),
        warnings=warnings,
        notes=["Nozzle side loads and detailed attachment geometry are future refinements."],
    )
