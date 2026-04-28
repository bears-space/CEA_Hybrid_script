"""High-level CFD planning, ingest, and correction workflow orchestration."""

from __future__ import annotations

from typing import Any, Mapping

from src.cfd.cfd_case_builder import build_cfd_case_definitions
from src.cfd.cfd_checks import build_cfd_validity_flags, collect_cfd_warnings
from src.cfd.cfd_corrections import (
    apply_correction_packages_to_config,
    correction_comparison_rows,
    correction_packages_from_results,
    filter_correction_packages,
    template_correction_packages_for_targets,
)
from src.cfd.cfd_export import write_cfd_outputs
from src.cfd.cfd_result_ingest import load_cfd_result_summaries
from src.cfd.cfd_targets import build_cfd_targets
from src.cfd.cfd_types import CfdCampaignPlan, CfdCorrectionPackage, CfdResultSummary
from src.hydraulic_validation.calibration_store import calibration_path_from_config
from src.io_utils import deep_merge
from src.injector_design.injector_types import InjectorGeometryDefinition
from src.nozzle_offdesign.nozzle_offdesign_types import NozzleOffDesignResult
from src.sizing.geometry_types import GeometryDefinition
from src.structural.structural_types import StructuralSizingResult
from src.thermal.thermal_types import ThermalSizingResult


def merge_cfd_config(
    study_config: Mapping[str, Any],
    override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the CFD config section after applying optional overrides."""

    override_section = dict(override or {})
    if "cfd" in override_section and isinstance(override_section["cfd"], Mapping):
        override_section = dict(override_section["cfd"])
    return deep_merge(dict(study_config.get("cfd", {})), override_section)


def _hydraulic_dependency_satisfied(study_config: Mapping[str, Any], cfd_config: Mapping[str, Any]) -> bool:
    if not bool(cfd_config.get("require_coldflow_before_stage1", False)):
        return True
    calibration_path = calibration_path_from_config(study_config)
    return calibration_path is not None and calibration_path.exists()


def _recommended_next_case(case_definitions) -> tuple[str | None, str | None]:
    pending = [case for case in case_definitions if case.status != "results_ingested"]
    if not pending:
        return None, None
    selected = min(pending, key=lambda case: (case.priority_rank, case.case_id))
    return selected.case_id, selected.target_definition.target_name


def _load_ingested_results(cfd_config: Mapping[str, Any]) -> tuple[list[CfdResultSummary], list[str]]:
    warnings: list[str] = []
    ingest_path = str(cfd_config.get("result_ingest_path", "")).strip()
    if not ingest_path:
        return [], warnings
    try:
        return load_cfd_result_summaries(ingest_path), warnings
    except Exception as exc:
        warnings.append(f"CFD result ingest failed: {exc}")
        return [], warnings


def run_cfd_workflow(
    study_config: Mapping[str, Any],
    cfd_config: Mapping[str, Any],
    output_dir: str,
    *,
    mode: str,
    geometry: GeometryDefinition,
    nominal_payload: Mapping[str, Any],
    injector_geometry: InjectorGeometryDefinition | None = None,
    structural_result: StructuralSizingResult | None = None,
    thermal_result: ThermalSizingResult | None = None,
    nozzle_result: NozzleOffDesignResult | None = None,
    corner_payload: Mapping[str, Any] | None = None,
    ballistics_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the CFD planning / ingest / correction workflow."""

    del structural_result
    target_definitions, warnings = build_cfd_targets(cfd_config)
    ingested_results, ingest_warnings = _load_ingested_results(cfd_config)
    warnings.extend(ingest_warnings)
    ingested_case_ids = {summary.case_id for summary in ingested_results}

    case_definitions, case_warnings = build_cfd_case_definitions(
        target_definitions,
        cfd_config=cfd_config,
        geometry=geometry,
        nominal_payload=nominal_payload,
        injector_geometry=injector_geometry,
        corner_payload=corner_payload,
        ballistics_payload=ballistics_payload,
        nozzle_result=nozzle_result,
        thermal_result=thermal_result,
        ingested_case_ids=ingested_case_ids,
        mode=mode,
    )
    warnings.extend(case_warnings)

    actual_corrections = correction_packages_from_results(ingested_results)
    if actual_corrections:
        all_corrections: list[CfdCorrectionPackage] = actual_corrections
    elif bool(cfd_config.get("generate_correction_templates", True)):
        all_corrections = template_correction_packages_for_targets(target_definitions)
    else:
        all_corrections = []
    filtered_corrections = filter_correction_packages(all_corrections, str(cfd_config.get("cfd_corrections_source", "combined")))

    updated_config = None
    comparison_rows: list[dict[str, Any]] = []
    if mode == "cfd_apply_corrections":
        updated_config = apply_correction_packages_to_config(study_config, filtered_corrections)
        comparison_rows = correction_comparison_rows(study_config, updated_config, filtered_corrections)

    recommended_next_case_id, recommended_next_target_name = _recommended_next_case(case_definitions)
    validity_flags = build_cfd_validity_flags(
        targets_present=bool(target_definitions),
        case_definitions=case_definitions,
        cfd_config=cfd_config,
        injector_geometry_available=injector_geometry is not None,
        ballistics_available=ballistics_payload is not None,
        nozzle_result_available=nozzle_result is not None,
        hydraulic_dependency_satisfied=_hydraulic_dependency_satisfied(study_config, cfd_config),
        ingested_results=ingested_results,
        correction_packages=filtered_corrections,
        mode=mode,
    )

    preliminary_plan = CfdCampaignPlan(
        campaign_name="default_cfd_campaign",
        case_source=str(cfd_config.get("cfd_case_source", "nominal_workflow")),
        corrections_source=str(cfd_config.get("cfd_corrections_source", "combined")),
        targets=target_definitions,
        stage_order=[f"{target.priority_rank}: {target.target_name}" for target in target_definitions],
        recommended_next_case_id=recommended_next_case_id,
        recommended_next_target_name=recommended_next_target_name,
        ingested_result_case_ids=sorted(ingested_case_ids),
        validity_flags=validity_flags,
        cfd_plan_valid=all(validity_flags.values()),
        warnings=warnings,
        failure_reason=None if all(validity_flags.values()) else "One or more CFD planning checks failed.",
        notes=[
            "CFD remains a supporting layer for targeted local questions; it does not replace the reduced-order workflow backbone.",
            "Default campaign order is injector, then head-end, then nozzle, then broader reacting internal flow.",
        ],
    )
    final_plan = CfdCampaignPlan(
        campaign_name=preliminary_plan.campaign_name,
        case_source=preliminary_plan.case_source,
        corrections_source=preliminary_plan.corrections_source,
        targets=preliminary_plan.targets,
        stage_order=preliminary_plan.stage_order,
        recommended_next_case_id=preliminary_plan.recommended_next_case_id,
        recommended_next_target_name=preliminary_plan.recommended_next_target_name,
        ingested_result_case_ids=preliminary_plan.ingested_result_case_ids,
        validity_flags=preliminary_plan.validity_flags,
        cfd_plan_valid=preliminary_plan.cfd_plan_valid,
        warnings=collect_cfd_warnings(preliminary_plan, case_definitions, ingested_results),
        failure_reason=preliminary_plan.failure_reason,
        notes=preliminary_plan.notes,
    )
    destination = write_cfd_outputs(
        output_dir,
        plan=final_plan,
        case_definitions=case_definitions,
        correction_packages=filtered_corrections,
        result_summaries=ingested_results,
        comparison_rows=comparison_rows,
        updated_config=updated_config,
    )
    return {
        "output_dir": destination,
        "plan": final_plan,
        "case_definitions": case_definitions,
        "result_summaries": ingested_results,
        "correction_packages": filtered_corrections,
        "updated_config": updated_config,
        "comparison_rows": comparison_rows,
    }
