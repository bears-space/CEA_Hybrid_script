"""Injector-plate structural placeholder checks."""

from __future__ import annotations

import math
from typing import Any, Mapping

from src.injector_design.injector_types import InjectorGeometryDefinition
from src.sizing.geometry_types import GeometryDefinition
from src.structural.closure_sizing import circular_plate_bending_stress_pa, required_circular_plate_thickness_m
from src.structural.pressure_vessel import round_up_to_increment
from src.structural.structural_types import InjectorPlateSizingResult, MaterialDefinition, StructuralDesignPolicy, StructuralLoadCase


def size_injector_plate(
    structural_config: Mapping[str, Any],
    geometry: GeometryDefinition,
    load_case: StructuralLoadCase,
    material: MaterialDefinition,
    policy: StructuralDesignPolicy,
    injector_geometry: InjectorGeometryDefinition | None = None,
) -> InjectorPlateSizingResult:
    """Run a conservative injector-plate thickness check using the current pressure budget."""

    settings = dict(structural_config.get("injector_plate", {}))
    warnings: list[str] = []
    notes: list[str] = ["Perforated-plate FEA is deferred; this is a conservative plate-bending placeholder."]

    unsupported_diameter_m = settings.get("unsupported_diameter_m")
    if unsupported_diameter_m is None:
        if injector_geometry is not None:
            unsupported_diameter_m = float(injector_geometry.active_face_diameter_m)
            notes.append("Unsupported span taken from synthesized injector active-face diameter.")
        else:
            unsupported_diameter_m = float(geometry.injector_face_diameter_m) * float(settings["unsupported_diameter_scale"])
            notes.append("Unsupported span taken from the frozen injector-face diameter and structural.injector_plate scale.")

    open_area_ratio = 0.0 if injector_geometry is None else float(injector_geometry.geometric_open_area_ratio)
    perforation_stress_multiplier = 1.0 + float(settings["perforation_stress_multiplier_factor"]) * open_area_ratio
    pressure_delta_pa = max(float(load_case.injector_delta_p_pa), 0.0)
    base_required_m = required_circular_plate_thickness_m(
        pressure_delta_pa,
        float(unsupported_diameter_m),
        float(material.allowable_stress_pa),
        model_type=policy.injector_plate_model_type,
        poisson_ratio=material.poisson_ratio,
    )
    required_thickness_m = base_required_m * math.sqrt(perforation_stress_multiplier)

    selected_thickness_m = settings.get("selected_thickness_m")
    if selected_thickness_m is None:
        if injector_geometry is not None:
            selected_thickness_m = float(injector_geometry.plate_thickness_m)
            notes.append("Selected thickness taken from the synthesized injector geometry.")
        else:
            selected_thickness_m = float(geometry.injector_plate_thickness_m)
            notes.append("Selected thickness taken from the frozen geometry injector plate thickness.")
    selected_thickness_m = round_up_to_increment(
        max(
            float(selected_thickness_m),
            required_thickness_m + float(policy.corrosion_or_manufacturing_allowance_m),
            float(policy.minimum_flange_thickness_m),
        ),
        float(policy.thickness_roundup_increment_m),
    )
    estimated_bending_stress_pa = circular_plate_bending_stress_pa(
        pressure_delta_pa,
        float(unsupported_diameter_m),
        selected_thickness_m,
        model_type=policy.injector_plate_model_type,
        poisson_ratio=material.poisson_ratio,
    ) * perforation_stress_multiplier
    margin_to_allowable = float(material.allowable_stress_pa) / max(estimated_bending_stress_pa, 1.0e-12) - 1.0
    if open_area_ratio >= float(settings["open_area_warning_threshold"]):
        warnings.append(
            f"Injector plate open-area ratio {open_area_ratio:.3f} exceeds the warning threshold "
            f"{float(settings['open_area_warning_threshold']):.3f}."
        )
    valid = bool(selected_thickness_m >= required_thickness_m and margin_to_allowable >= 0.0)
    if injector_geometry is None:
        warnings.append("Injector geometry was not available; injector-plate sizing fell back to frozen geometry assumptions.")

    return InjectorPlateSizingResult(
        material_name=material.material_name,
        allowable_stress_pa=float(material.allowable_stress_pa),
        pressure_delta_pa=pressure_delta_pa,
        unsupported_diameter_m=float(unsupported_diameter_m),
        hole_count=(
            int(geometry.injector_hole_count)
            if injector_geometry is None and geometry.injector_hole_count is not None
            else (None if injector_geometry is None else int(injector_geometry.hole_count))
        ),
        hole_diameter_m=(
            float(geometry.injector_hole_diameter_m)
            if injector_geometry is None and geometry.injector_hole_diameter_m is not None
            else (None if injector_geometry is None else float(injector_geometry.hole_diameter_m))
        ),
        open_area_ratio=float(open_area_ratio),
        perforation_stress_multiplier=float(perforation_stress_multiplier),
        required_thickness_m=float(required_thickness_m),
        selected_thickness_m=float(selected_thickness_m),
        estimated_bending_stress_pa=float(estimated_bending_stress_pa),
        margin_to_allowable=float(margin_to_allowable),
        model_type=policy.injector_plate_model_type,
        valid=valid,
        warnings=warnings,
        notes=notes,
    )
