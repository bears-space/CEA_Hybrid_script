"""Closure-retention placeholder sizing for bolted or tie-rod joints."""

from __future__ import annotations

import math
from typing import Any, Mapping

from src.structural.structural_types import FastenerSizingResult, MaterialDefinition, StructuralDesignPolicy, StructuralLoadCase


def _tensile_area_per_fastener_m2(nominal_diameter_m: float, tensile_area_factor: float) -> float:
    return math.pi * 0.25 * float(nominal_diameter_m) ** 2 * float(tensile_area_factor)


def size_fasteners(
    structural_config: Mapping[str, Any],
    load_case: StructuralLoadCase,
    material: MaterialDefinition,
    policy: StructuralDesignPolicy,
) -> FastenerSizingResult:
    """Estimate closure-retention loads for the selected bolted or tie-rod concept."""

    retention_type = str(structural_config.get("closure_style", policy.closure_style))
    if retention_type == "monolithic":
        return FastenerSizingResult(
            retention_type="monolithic",
            material_name=None,
            separating_force_n=float(load_case.closure_separating_force_n),
            fastener_count=0,
            nominal_diameter_m=None,
            tensile_area_per_fastener_m2=None,
            external_load_per_fastener_n=None,
            preload_target_per_fastener_n=None,
            required_fastener_count=None,
            allowable_tensile_stress_pa=None,
            estimated_tensile_stress_pa=None,
            margin_to_allowable=None,
            preload_margin=None,
            valid=True,
            warnings=[],
            notes=["Monolithic closure selected; discrete fastener sizing is not applicable."],
        )

    settings = dict(structural_config.get("fasteners", {}))
    warnings: list[str] = []
    fastener_count = int(settings["fastener_count"])
    if fastener_count <= 0:
        return FastenerSizingResult(
            retention_type=retention_type,
            material_name=material.material_name,
            separating_force_n=float(load_case.closure_separating_force_n),
            fastener_count=fastener_count,
            nominal_diameter_m=float(settings["nominal_diameter_m"]),
            tensile_area_per_fastener_m2=None,
            external_load_per_fastener_n=None,
            preload_target_per_fastener_n=None,
            required_fastener_count=None,
            allowable_tensile_stress_pa=float(material.allowable_stress_pa),
            estimated_tensile_stress_pa=None,
            margin_to_allowable=None,
            preload_margin=None,
            valid=False,
            warnings=["Fastener count must be positive for retained closures."],
            notes=[],
        )

    tensile_area_m2 = _tensile_area_per_fastener_m2(
        float(settings["nominal_diameter_m"]),
        float(settings["tensile_area_factor"]),
    )
    external_joint_load_n = float(load_case.closure_separating_force_n) * float(settings["joint_load_fraction"])
    external_load_per_fastener_n = external_joint_load_n / float(fastener_count)
    allowable_tensile_stress_pa = float(material.allowable_stress_pa)
    estimated_tensile_stress_pa = external_load_per_fastener_n / max(tensile_area_m2, 1.0e-12)
    required_fastener_count = int(math.ceil(external_joint_load_n / max(allowable_tensile_stress_pa * tensile_area_m2, 1.0e-12)))
    proof_strength_pa = min(
        float(material.yield_strength_pa),
        float(material.ultimate_strength_pa) / float(policy.proof_factor),
    )
    preload_target_per_fastener_n = float(policy.default_bolt_preload_fraction) * proof_strength_pa * tensile_area_m2
    preload_margin = (float(fastener_count) * preload_target_per_fastener_n) / max(float(load_case.closure_separating_force_n), 1.0e-12) - 1.0
    margin_to_allowable = allowable_tensile_stress_pa / max(estimated_tensile_stress_pa, 1.0e-12) - 1.0
    valid = bool(required_fastener_count <= fastener_count and margin_to_allowable >= 0.0)
    if required_fastener_count > fastener_count:
        warnings.append("Configured fastener count is below the estimated required count for the closure separating load.")
    if preload_margin < 0.0:
        warnings.append("Estimated total fastener preload is below the closure separating force.")
    return FastenerSizingResult(
        retention_type=retention_type,
        material_name=material.material_name,
        separating_force_n=float(load_case.closure_separating_force_n),
        fastener_count=fastener_count,
        nominal_diameter_m=float(settings["nominal_diameter_m"]),
        tensile_area_per_fastener_m2=float(tensile_area_m2),
        external_load_per_fastener_n=float(external_load_per_fastener_n),
        preload_target_per_fastener_n=float(preload_target_per_fastener_n),
        required_fastener_count=required_fastener_count,
        allowable_tensile_stress_pa=allowable_tensile_stress_pa,
        estimated_tensile_stress_pa=float(estimated_tensile_stress_pa),
        margin_to_allowable=float(margin_to_allowable),
        preload_margin=float(preload_margin),
        valid=valid,
        warnings=warnings,
        notes=["Simplified axial separating-load split only; detailed bolted-joint analysis is a future refinement."],
    )
