"""Aggregate checks and validity flags for the structural sizing workflow."""

from __future__ import annotations

from src.structural.structural_types import StructuralSizingResult


def build_validity_flags(result: StructuralSizingResult) -> dict[str, bool]:
    """Return named validity flags for the major structural subsystems."""

    return {
        "chamber_wall_valid": bool(result.chamber_wall_result.valid),
        "forward_closure_valid": bool(result.forward_closure_result.valid),
        "aft_closure_valid": bool(result.aft_closure_result.valid),
        "injector_plate_valid": bool(result.injector_plate_result.valid),
        "fastener_valid": bool(result.fastener_result.valid),
        "nozzle_mount_valid": bool(result.nozzle_mount_result.valid),
        "grain_support_valid": bool(result.grain_support_result.valid),
        "explicit_governing_load_case": bool(result.governing_load_case.case_name),
    }


def collect_structural_warnings(result: StructuralSizingResult) -> list[str]:
    """Flatten warnings across the structural result tree."""

    warnings = list(result.warnings)
    warnings.extend(result.chamber_wall_result.warnings)
    warnings.extend(result.forward_closure_result.warnings)
    warnings.extend(result.aft_closure_result.warnings)
    warnings.extend(result.injector_plate_result.warnings)
    warnings.extend(result.fastener_result.warnings)
    warnings.extend(result.nozzle_mount_result.warnings)
    warnings.extend(result.grain_support_result.warnings)
    seen: list[str] = []
    for warning in warnings:
        if warning not in seen:
            seen.append(warning)
    return seen
