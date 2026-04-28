"""Validity flags and warnings for CFD campaign planning and result ingestion."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from src.cfd.cfd_types import CfdCampaignPlan, CfdCaseDefinition, CfdCorrectionPackage, CfdResultSummary


def build_cfd_validity_flags(
    *,
    targets_present: bool,
    case_definitions: Sequence[CfdCaseDefinition],
    cfd_config: Mapping[str, Any],
    injector_geometry_available: bool,
    ballistics_available: bool,
    nozzle_result_available: bool,
    hydraulic_dependency_satisfied: bool,
    ingested_results: Sequence[CfdResultSummary],
    correction_packages: Sequence[CfdCorrectionPackage],
    mode: str,
) -> dict[str, bool]:
    """Build named validity flags for the CFD planning workflow."""

    requires_ingest = mode in {"cfd_ingest_results", "cfd_apply_corrections"}
    target_order = [case.priority_rank for case in case_definitions]
    contiguous_priorities = target_order == sorted(target_order)
    return {
        "targets_present": bool(targets_present),
        "case_definitions_present": bool(case_definitions),
        "target_order_defined": contiguous_priorities,
        "geometry_packages_valid": all(all(case.geometry_package.validity_flags.values()) for case in case_definitions),
        "boundary_packages_valid": all(all(case.boundary_conditions.validity_flags.values()) for case in case_definitions),
        "injector_geometry_available_if_needed": (
            injector_geometry_available
            or all(case.target_definition.target_category not in {"injector_plenum", "headend_prechamber"} for case in case_definitions)
        ),
        "internal_ballistics_dependency_satisfied": (
            ballistics_available
            or not bool(cfd_config.get("require_internal_ballistics_before_stage2", True))
            or all(case.target_definition.target_category not in {"headend_prechamber", "reacting_internal_region"} for case in case_definitions)
        ),
        "nozzle_dependency_satisfied": (
            nozzle_result_available
            or not bool(cfd_config.get("require_nozzle_offdesign_before_stage3", True))
            or all(case.target_definition.target_category != "nozzle_local" for case in case_definitions)
        ),
        "hydraulic_dependency_satisfied": hydraulic_dependency_satisfied,
        "result_ingest_available_if_requested": (not requires_ingest) or bool(ingested_results),
        "corrections_linked_to_modules": all(bool(package.downstream_target_module) for package in correction_packages),
    }


def collect_cfd_warnings(
    plan: CfdCampaignPlan,
    case_definitions: Sequence[CfdCaseDefinition],
    ingested_results: Sequence[CfdResultSummary],
) -> list[str]:
    """Collect flattened CFD workflow warnings."""

    warnings = list(plan.warnings)
    for case in case_definitions:
        if not all(case.geometry_package.validity_flags.values()):
            warnings.append(f"Geometry package for case '{case.case_id}' is incomplete.")
        if not all(case.boundary_conditions.validity_flags.values()):
            warnings.append(f"Boundary-condition package for case '{case.case_id}' is incomplete.")
    for result in ingested_results:
        warnings.extend(result.warnings)
    deduped: list[str] = []
    for warning in warnings:
        if warning not in deduped:
            deduped.append(warning)
    return deduped
