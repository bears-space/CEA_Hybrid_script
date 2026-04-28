"""Aggregate validity flags and warnings for the thermal workflow."""

from __future__ import annotations

from src.thermal.thermal_types import ThermalSizingResult


def build_validity_flags(result: ThermalSizingResult) -> dict[str, bool]:
    """Return named validity flags for the major thermal subsystems."""

    return {
        "explicit_governing_load_case": bool(result.governing_load_case.case_name),
        "chamber_region_valid": bool(result.chamber_region_result.region.valid),
        "prechamber_valid": True if result.prechamber_result is None else bool(result.prechamber_result.region.valid),
        "postchamber_valid": True if result.postchamber_result is None else bool(result.postchamber_result.region.valid),
        "throat_valid": bool(result.throat_result.region.valid),
        "diverging_nozzle_valid": bool(result.diverging_nozzle_result.region.valid),
        "injector_face_valid": True if result.injector_face_result is None else bool(result.injector_face_result.region.valid),
        "throat_explicitly_evaluated": True,
        "injector_face_explicitly_evaluated": result.injector_face_result is not None,
        "governing_margin_identified": bool(result.summary_margins),
    }


def collect_thermal_warnings(result: ThermalSizingResult) -> list[str]:
    """Flatten warnings across the thermal result tree."""

    warnings = list(result.warnings)
    warnings.extend(result.chamber_region_result.region.warnings)
    if result.prechamber_result is not None:
        warnings.extend(result.prechamber_result.region.warnings)
    if result.postchamber_result is not None:
        warnings.extend(result.postchamber_result.region.warnings)
    warnings.extend(result.throat_result.region.warnings)
    warnings.extend(result.diverging_nozzle_result.region.warnings)
    if result.injector_face_result is not None:
        warnings.extend(result.injector_face_result.region.warnings)
    if result.optional_liner_result is not None:
        warnings.extend(result.optional_liner_result.warnings)
    if result.optional_throat_insert_result is not None:
        warnings.extend(result.optional_throat_insert_result.warnings)
    deduped: list[str] = []
    for warning in warnings:
        if warning not in deduped:
            deduped.append(warning)
    return deduped
