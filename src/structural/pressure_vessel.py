"""Closed-form chamber-wall sizing helpers."""

from __future__ import annotations

import math

from src.structural.structural_types import ChamberSizingResult, MaterialDefinition, StructuralDesignPolicy, StructuralLoadCase


def round_up_to_increment(value_m: float, increment_m: float) -> float:
    if increment_m <= 0.0:
        return float(value_m)
    return math.ceil(float(value_m) / float(increment_m)) * float(increment_m)


def thick_wall_required_thickness_m(inner_radius_m: float, pressure_pa: float, allowable_stress_pa: float) -> float:
    if allowable_stress_pa <= pressure_pa:
        raise ValueError("Allowable stress must exceed pressure for thick-wall sizing.")
    outer_radius_m = inner_radius_m * math.sqrt((allowable_stress_pa + pressure_pa) / (allowable_stress_pa - pressure_pa))
    return max(outer_radius_m - inner_radius_m, 0.0)


def size_chamber_wall(
    load_case: StructuralLoadCase,
    chamber_id_m: float,
    material: MaterialDefinition,
    policy: StructuralDesignPolicy,
) -> ChamberSizingResult:
    """Size the chamber wall using thin-wall logic with a thick-wall fallback."""

    warnings: list[str] = []
    notes: list[str] = []
    allowable_stress_pa = float(material.allowable_stress_pa)
    chamber_radius_m = 0.5 * float(chamber_id_m)
    pressure_pa = max(float(load_case.chamber_pressure_pa) - float(load_case.ambient_pressure_pa), 0.0)
    if chamber_radius_m <= 0.0 or allowable_stress_pa <= 0.0:
        raise ValueError("Positive chamber radius and allowable stress are required for chamber sizing.")

    required_thickness_m = pressure_pa * chamber_radius_m / allowable_stress_pa
    thin_wall_ratio = chamber_radius_m / max(required_thickness_m, 1.0e-12)
    thin_wall_valid = thin_wall_ratio >= float(policy.thin_wall_switch_ratio)
    method_used = "thin_wall_closed_cylinder"
    if not thin_wall_valid:
        required_thickness_m = thick_wall_required_thickness_m(chamber_radius_m, pressure_pa, allowable_stress_pa)
        method_used = "thick_wall_lame"
        warnings.append("Thin-wall assumptions are not valid at the required chamber thickness; using a thick-wall fallback.")
    notes.append(f"Sizing method: {method_used}.")

    minimum_selected_m = max(
        float(policy.minimum_wall_thickness_m),
        required_thickness_m + float(policy.corrosion_or_manufacturing_allowance_m),
    )
    selected_thickness_m = round_up_to_increment(minimum_selected_m, float(policy.thickness_roundup_increment_m))
    outer_radius_m = chamber_radius_m + selected_thickness_m
    if method_used == "thick_wall_lame":
        hoop_stress_pa = pressure_pa * (
            (outer_radius_m**2 + chamber_radius_m**2) / max(outer_radius_m**2 - chamber_radius_m**2, 1.0e-12)
        )
    else:
        hoop_stress_pa = pressure_pa * chamber_radius_m / max(selected_thickness_m, 1.0e-12)
    axial_stress_pa = pressure_pa * chamber_radius_m / max(2.0 * selected_thickness_m, 1.0e-12)
    governing_stress_pa = max(hoop_stress_pa, axial_stress_pa)
    margin_to_allowable = allowable_stress_pa / max(governing_stress_pa, 1.0e-12) - 1.0
    valid = bool(selected_thickness_m >= required_thickness_m and margin_to_allowable >= 0.0 and selected_thickness_m > 0.0)
    if selected_thickness_m < required_thickness_m:
        warnings.append("Selected chamber-wall thickness is below the required thickness.")

    return ChamberSizingResult(
        material_name=material.material_name,
        allowable_stress_pa=allowable_stress_pa,
        chamber_pressure_pa=float(load_case.chamber_pressure_pa),
        chamber_radius_m=chamber_radius_m,
        required_thickness_m=float(required_thickness_m),
        selected_thickness_m=float(selected_thickness_m),
        hoop_stress_pa=float(hoop_stress_pa),
        axial_stress_pa=float(axial_stress_pa),
        governing_stress_pa=float(governing_stress_pa),
        margin_to_allowable=float(margin_to_allowable),
        thin_wall_ratio=float(thin_wall_ratio),
        thin_wall_valid=bool(thin_wall_valid),
        method_used=method_used,
        valid=valid,
        warnings=warnings,
        notes=notes,
    )
