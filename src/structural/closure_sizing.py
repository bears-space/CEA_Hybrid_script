"""Simplified circular-plate closure sizing helpers."""

from __future__ import annotations

import math

from src.structural.pressure_vessel import round_up_to_increment
from src.structural.structural_types import ClosureSizingResult, MaterialDefinition, StructuralDesignPolicy


def plate_bending_stress_factor(model_type: str, poisson_ratio: float | None) -> float:
    nu = 0.33 if poisson_ratio is None else float(poisson_ratio)
    if model_type == "clamped_circular_plate":
        return (3.0 + nu) / 8.0
    if model_type == "simply_supported_circular_plate":
        return (3.0 + nu) / 4.0
    raise ValueError(f"Unsupported circular-plate model: {model_type}")


def required_circular_plate_thickness_m(
    pressure_pa: float,
    loaded_diameter_m: float,
    allowable_stress_pa: float,
    *,
    model_type: str,
    poisson_ratio: float | None,
) -> float:
    radius_m = 0.5 * float(loaded_diameter_m)
    factor = plate_bending_stress_factor(model_type, poisson_ratio)
    return radius_m * math.sqrt(max(factor * float(pressure_pa) / max(float(allowable_stress_pa), 1.0e-12), 0.0))


def circular_plate_bending_stress_pa(
    pressure_pa: float,
    loaded_diameter_m: float,
    thickness_m: float,
    *,
    model_type: str,
    poisson_ratio: float | None,
) -> float:
    radius_m = 0.5 * float(loaded_diameter_m)
    factor = plate_bending_stress_factor(model_type, poisson_ratio)
    return factor * float(pressure_pa) * radius_m**2 / max(float(thickness_m) ** 2, 1.0e-12)


def size_closure(
    *,
    closure_name: str,
    chamber_pressure_pa: float,
    ambient_pressure_pa: float,
    loaded_diameter_m: float,
    material: MaterialDefinition,
    policy: StructuralDesignPolicy,
    model_type: str,
    minimum_thickness_m: float | None = None,
    notes: list[str] | None = None,
) -> ClosureSizingResult:
    """Size a pressure-loaded circular closure using a simple plate model."""

    warnings: list[str] = []
    note_list = list(notes or [])
    pressure_pa = max(float(chamber_pressure_pa) - float(ambient_pressure_pa), 0.0)
    minimum_selected_m = float(policy.minimum_flange_thickness_m if minimum_thickness_m is None else minimum_thickness_m)
    required_thickness_m = required_circular_plate_thickness_m(
        pressure_pa,
        loaded_diameter_m,
        material.allowable_stress_pa,
        model_type=model_type,
        poisson_ratio=material.poisson_ratio,
    )
    selected_thickness_m = round_up_to_increment(
        max(required_thickness_m + float(policy.corrosion_or_manufacturing_allowance_m), minimum_selected_m),
        float(policy.thickness_roundup_increment_m),
    )
    estimated_bending_stress_pa = circular_plate_bending_stress_pa(
        pressure_pa,
        loaded_diameter_m,
        selected_thickness_m,
        model_type=model_type,
        poisson_ratio=material.poisson_ratio,
    )
    projected_area_m2 = math.pi * (0.5 * float(loaded_diameter_m)) ** 2
    separating_force_n = pressure_pa * projected_area_m2
    margin_to_allowable = float(material.allowable_stress_pa) / max(estimated_bending_stress_pa, 1.0e-12) - 1.0
    valid = bool(selected_thickness_m >= required_thickness_m and margin_to_allowable >= 0.0)
    if loaded_diameter_m <= 0.0:
        warnings.append(f"{closure_name} loaded diameter is non-physical.")
        valid = False
    if selected_thickness_m < required_thickness_m:
        warnings.append(f"{closure_name} selected thickness is below the required thickness.")
    return ClosureSizingResult(
        closure_name=closure_name,
        material_name=material.material_name,
        allowable_stress_pa=float(material.allowable_stress_pa),
        chamber_pressure_pa=float(chamber_pressure_pa),
        loaded_diameter_m=float(loaded_diameter_m),
        projected_area_m2=float(projected_area_m2),
        separating_force_n=float(separating_force_n),
        required_thickness_m=float(required_thickness_m),
        selected_thickness_m=float(selected_thickness_m),
        estimated_bending_stress_pa=float(estimated_bending_stress_pa),
        margin_to_allowable=float(margin_to_allowable),
        model_type=model_type,
        valid=valid,
        warnings=warnings,
        notes=note_list,
    )
