"""Mode handlers for the shared workflow runner."""

from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any

from src.constants import (
    ANALYSIS_DIRNAME,
    CFD_DIRNAME,
    GEOMETRY_DIRNAME,
    HYDRAULIC_VALIDATION_DIRNAME,
    INJECTOR_DESIGN_DIRNAME,
    INTERNAL_BALLISTICS_DIRNAME,
    NOZZLE_OFFDESIGN_DIRNAME,
    PERFORMANCE_DIRNAME,
    STRUCTURAL_DIRNAME,
    TESTING_DIRNAME,
    THERMAL_DIRNAME,
    THERMOCHEMISTRY_DIRNAME,
)
from src.io_utils import ensure_directory, write_json
from src.workflows.runtime import WorkflowContext

LOGGER = logging.getLogger(__name__)


def _result(context: WorkflowContext, payload: dict[str, Any]) -> dict[str, Any]:
    return {"mode": context.mode, "run": context.run, "payload": payload}


def handle_cea(context: WorkflowContext) -> dict[str, Any]:
    from src.cea.cea_interface import get_cea_performance_point, run_cea_study, write_cea_outputs
    from src.workflows.exporters import _run_cea_mode

    if context.cea_override is not None:
        output_dir = ensure_directory(context.run.root / THERMOCHEMISTRY_DIRNAME)
        sweep_result = run_cea_study(deepcopy(dict(context.cea_override)))
        write_json(output_dir / "cea_config_used.json", deepcopy(dict(context.cea_override)))
        write_cea_outputs(output_dir, deepcopy(dict(context.cea_override)), sweep_result)
        highest_isp = get_cea_performance_point(sweep_result)
        write_json(output_dir / "highest_isp_case.json", highest_isp.raw)
        payload = {
            "output_dir": output_dir,
            "case_count": len(sweep_result.cases),
            "failure_count": len(sweep_result.failures),
            "best_isp_s": highest_isp.isp_s,
        }
    else:
        payload = _run_cea_mode(context.cea_config_path, context.run.root)
    context.run.register_section(THERMOCHEMISTRY_DIRNAME, payload["output_dir"])
    context.run.write_manifest(
        status="completed",
        summary={
            "case_count": payload["case_count"],
            "failure_count": payload["failure_count"],
            "best_isp_s": payload["best_isp_s"],
        },
        config_paths=context.config_paths,
    )
    return _result(context, payload)


def handle_nominal(context: WorkflowContext) -> dict[str, Any]:
    from src.workflows.exporters import _export_nominal_run

    payload = _export_nominal_run(context.study_config, context.run.root)
    context.run.register_section(PERFORMANCE_DIRNAME, payload["output_dir"])
    context.run.write_manifest(
        status="completed",
        summary={
            "status": payload["metrics"]["status"],
            "stop_reason": payload["metrics"]["stop_reason"],
            "thrust_avg_n": payload["metrics"]["thrust_avg_n"],
            "impulse_total_ns": payload["metrics"]["impulse_total_ns"],
            "constraints_pass": payload["constraints"]["all_pass"],
        },
        config_paths=context.config_paths,
    )
    return _result(context, payload)


def handle_oat(context: WorkflowContext) -> dict[str, Any]:
    from src.workflows.exporters import _export_sensitivity_run

    payload = _export_sensitivity_run(context.study_config, context.run.root)
    context.run.register_section(ANALYSIS_DIRNAME, payload["output_dir"])
    context.run.write_manifest(
        status="completed",
        summary={"case_count": len(payload["cases"]), "ranking_count": len(payload["rankings"])},
        config_paths=context.config_paths,
    )
    return _result(context, payload)


def handle_corners(context: WorkflowContext) -> dict[str, Any]:
    from src.workflows.exporters import _export_corner_run

    payload = _export_corner_run(context.study_config, context.run.root)
    context.run.register_section(ANALYSIS_DIRNAME, payload["output_dir"])
    context.run.write_manifest(
        status="completed",
        summary={"case_count": len(payload["corners"]), "constraints_pass": payload["nominal"]["constraints"]["all_pass"]},
        config_paths=context.config_paths,
    )
    return _result(context, payload)


def handle_geometry(context: WorkflowContext) -> dict[str, Any]:
    from src.workflows.exporters import _export_geometry_run

    payload = _export_geometry_run(context.study_config, context.cea_config_path, context.run.root, cea_config_override=context.cea_override)
    context.run.register_section(GEOMETRY_DIRNAME, payload["output_dir"])
    context.run.write_manifest(
        status="completed",
        summary={
            "geometry_valid": payload["geometry"].geometry_valid,
            "chamber_id_m": payload["geometry"].chamber_id_m,
            "grain_length_m": payload["geometry"].grain_length_m,
            "lstar_initial_m": payload["geometry"].lstar_initial_m,
        },
        config_paths=context.config_paths,
    )
    return _result(context, payload)


def handle_internal_ballistics(context: WorkflowContext) -> dict[str, Any]:
    from src.workflows.exporters import _export_ballistics_run

    payload = _export_ballistics_run(context.study_config, context.cea_config_path, context.run.root, cea_config_override=context.cea_override)
    context.run.register_section(INTERNAL_BALLISTICS_DIRNAME, payload["output_dir"])
    metrics = payload["payload"]["metrics"]
    context.run.write_manifest(
        status="completed",
        summary={
            "status": metrics["status"],
            "stop_reason": metrics["stop_reason"],
            "thrust_avg_n": metrics["thrust_avg_n"],
            "impulse_total_ns": metrics["impulse_total_ns"],
            "pc_avg_bar": metrics["pc_avg_bar"],
            "geometry_valid": metrics["geometry_valid"],
        },
        config_paths=context.config_paths,
    )
    return _result(context, payload)


def handle_injector_design(context: WorkflowContext) -> dict[str, Any]:
    from src.workflows.exporters import _export_injector_run

    payload = _export_injector_run(context.study_config, context.cea_config_path, context.run.root, cea_config_override=context.cea_override)
    context.run.register_section(INJECTOR_DESIGN_DIRNAME, payload["output_dir"])
    geometry = payload["payload"]["injector_geometry"]
    effective_model = payload["payload"]["effective_model"]
    context.run.write_manifest(
        status="completed",
        summary={
            "injector_geometry_valid": geometry.injector_geometry_valid,
            "hole_count": geometry.hole_count,
            "hole_diameter_m": geometry.hole_diameter_m,
            "effective_cda_m2": effective_model.effective_cda_m2,
        },
        config_paths=context.config_paths,
    )
    return _result(context, payload)


def handle_hydraulic_predict(context: WorkflowContext) -> dict[str, Any]:
    from src.hydraulic_validation import run_hydraulic_prediction_workflow

    payload = run_hydraulic_prediction_workflow(context.study_config, context.hydraulic_config, context.run.root / HYDRAULIC_VALIDATION_DIRNAME)
    context.run.register_section(HYDRAULIC_VALIDATION_DIRNAME, payload["output_dir"])
    context.run.write_manifest(
        status="completed",
        summary={
            "dataset_name": payload["dataset"].dataset_name,
            "point_count": len(payload["dataset"].points),
            "mdot_rmse_percent": payload["baseline_stats"]["mdot_error_percent"]["rmse"],
        },
        config_paths=context.config_paths,
    )
    return _result(context, payload)


def handle_hydraulic_calibrate(context: WorkflowContext) -> dict[str, Any]:
    from src.hydraulic_validation import run_hydraulic_calibration_workflow

    payload = run_hydraulic_calibration_workflow(context.study_config, context.hydraulic_config, context.run.root / HYDRAULIC_VALIDATION_DIRNAME)
    context.run.register_section(HYDRAULIC_VALIDATION_DIRNAME, payload["output_dir"])
    package = payload["calibration_package"]
    context.run.write_manifest(
        status="completed",
        summary={
            "calibration_mode": package.calibration_mode,
            "calibration_valid": package.calibration_valid,
            "recommended_model_source": package.recommended_model_source,
            "mdot_rmse_percent": payload["calibrated_stats"]["mdot_error_percent"]["rmse"],
        },
        config_paths=context.config_paths,
    )
    return _result(context, payload)


def handle_hydraulic_compare(context: WorkflowContext) -> dict[str, Any]:
    from src.hydraulic_validation import run_hydraulic_compare_workflow

    payload = run_hydraulic_compare_workflow(context.study_config, context.hydraulic_config, context.run.root / HYDRAULIC_VALIDATION_DIRNAME)
    context.run.register_section(HYDRAULIC_VALIDATION_DIRNAME, payload["output_dir"])
    package = payload["calibration_package"]
    context.run.write_manifest(
        status="completed",
        summary={
            "comparison_mode": package.calibration_mode,
            "baseline_mdot_rmse_percent": payload["baseline_stats"]["mdot_error_percent"]["rmse"],
            "calibrated_mdot_rmse_percent": payload["calibrated_stats"]["mdot_error_percent"]["rmse"],
        },
        config_paths=context.config_paths,
    )
    return _result(context, payload)


def handle_structural_size(context: WorkflowContext) -> dict[str, Any]:
    from src.workflows.exporters import _export_structural_run

    payload = _export_structural_run(
        context.study_config,
        context.structural_config,
        context.cea_config_path,
        context.run.root,
        cea_config_override=context.cea_override,
    )
    context.run.register_section(STRUCTURAL_DIRNAME, payload["output_dir"])
    result = payload["payload"]["result"]
    context.run.write_manifest(
        status="completed",
        summary={
            "structural_valid": result.structural_valid,
            "governing_load_case": result.governing_load_case.case_name,
            "chamber_wall_thickness_mm": result.chamber_wall_result.selected_thickness_m * 1000.0,
            "total_structural_mass_estimate_kg": result.total_structural_mass_estimate_kg,
        },
        config_paths=context.config_paths,
    )
    return _result(context, payload)


def handle_thermal_size(context: WorkflowContext) -> dict[str, Any]:
    from src.workflows.exporters import _export_thermal_run

    payload = _export_thermal_run(
        context.study_config,
        context.structural_config,
        context.thermal_config,
        context.cea_config_path,
        context.run.root,
        cea_config_override=context.cea_override,
    )
    context.run.register_section(STRUCTURAL_DIRNAME, payload["structural_dependency"]["output_dir"])
    context.run.register_section(THERMAL_DIRNAME, payload["output_dir"])
    result = payload["payload"]["result"]
    context.run.write_manifest(
        status="completed",
        summary={
            "thermal_valid": result.thermal_valid,
            "governing_load_case": result.governing_load_case.case_name,
            "governing_region": min(result.summary_margins, key=result.summary_margins.get),
            "peak_throat_temp_k": result.throat_result.region.peak_inner_wall_temp_k,
            "total_thermal_protection_mass_estimate_kg": result.total_thermal_protection_mass_estimate_kg,
        },
        config_paths=context.config_paths,
    )
    return _result(context, payload)


def handle_nozzle_offdesign(context: WorkflowContext) -> dict[str, Any]:
    from src.workflows.exporters import _export_nozzle_offdesign_run

    payload = _export_nozzle_offdesign_run(
        context.study_config,
        context.structural_config,
        context.thermal_config,
        context.nozzle_offdesign_config,
        context.cea_config_path,
        context.run.root,
        cea_config_override=context.cea_override,
    )
    context.run.register_section(STRUCTURAL_DIRNAME, context.run.root / STRUCTURAL_DIRNAME)
    context.run.register_section(THERMAL_DIRNAME, context.run.root / THERMAL_DIRNAME)
    context.run.register_section(NOZZLE_OFFDESIGN_DIRNAME, payload["output_dir"])
    result = payload["payload"]["result"]
    context.run.write_manifest(
        status="completed",
        summary={
            "nozzle_offdesign_valid": result.nozzle_offdesign_valid,
            "governing_case": result.governing_case.case_name,
            "separation_risk": result.separation_result.risk_level,
            "recommended_usage_mode": result.recommendations.get("recommended_usage_mode"),
            "ground_test_suitable": result.recommendations.get("ground_test_suitable"),
            "flight_suitable": result.recommendations.get("flight_suitable"),
        },
        config_paths=context.config_paths,
    )
    return _result(context, payload)


def handle_cfd(context: WorkflowContext) -> dict[str, Any]:
    from src.workflows.exporters import _export_cfd_run

    payload = _export_cfd_run(
        context.study_config,
        context.structural_config,
        context.thermal_config,
        context.nozzle_offdesign_config,
        context.cfd_config,
        context.mode,
        context.cea_config_path,
        context.run.root,
        cea_config_override=context.cea_override,
    )
    if (context.run.root / GEOMETRY_DIRNAME).exists():
        context.run.register_section(GEOMETRY_DIRNAME, context.run.root / GEOMETRY_DIRNAME)
    context.run.register_section(STRUCTURAL_DIRNAME, context.run.root / STRUCTURAL_DIRNAME)
    context.run.register_section(THERMAL_DIRNAME, context.run.root / THERMAL_DIRNAME)
    context.run.register_section(NOZZLE_OFFDESIGN_DIRNAME, context.run.root / NOZZLE_OFFDESIGN_DIRNAME)
    context.run.register_section(CFD_DIRNAME, payload["output_dir"])
    plan = payload["payload"]["plan"]
    context.run.write_manifest(
        status="completed",
        summary={
            "cfd_plan_valid": plan.cfd_plan_valid,
            "recommended_next_case_id": plan.recommended_next_case_id,
            "recommended_next_target_name": plan.recommended_next_target_name,
            "case_definition_count": len(payload["payload"]["case_definitions"]),
            "correction_package_count": len(payload["payload"]["correction_packages"]),
            "ingested_result_count": len(payload["payload"]["result_summaries"]),
        },
        config_paths=context.config_paths,
    )
    return _result(context, payload)


def handle_testing(context: WorkflowContext) -> dict[str, Any]:
    from src.workflows.exporters import _export_testing_run

    payload = _export_testing_run(
        context.study_config,
        context.structural_config,
        context.thermal_config,
        context.nozzle_offdesign_config,
        context.cfd_config,
        context.testing_config,
        context.cea_config_path,
        context.run.root,
        cea_config_override=context.cea_override,
    )
    if (context.run.root / GEOMETRY_DIRNAME).exists():
        context.run.register_section(GEOMETRY_DIRNAME, context.run.root / GEOMETRY_DIRNAME)
    context.run.register_section(STRUCTURAL_DIRNAME, context.run.root / STRUCTURAL_DIRNAME)
    context.run.register_section(THERMAL_DIRNAME, context.run.root / THERMAL_DIRNAME)
    context.run.register_section(NOZZLE_OFFDESIGN_DIRNAME, context.run.root / NOZZLE_OFFDESIGN_DIRNAME)
    if (context.run.root / CFD_DIRNAME).exists():
        context.run.register_section(CFD_DIRNAME, context.run.root / CFD_DIRNAME)
    context.run.register_section(TESTING_DIRNAME, payload["output_dir"])
    campaign = payload["payload"]["campaign_plan"]
    readiness = payload["payload"]["readiness"]
    context.run.write_manifest(
        status="completed",
        summary={
            "test_progression_valid": campaign.test_progression_valid,
            "recommended_next_stage": campaign.recommended_next_stage,
            "recommended_next_test": readiness.recommended_next_test,
            "completed_stage_count": len(readiness.completed_stages),
            "comparison_count": len(payload["payload"]["comparisons"]),
            "calibration_package_count": len(payload["payload"]["calibration_packages"]),
            "overall_readiness_flag": readiness.overall_readiness_flag,
        },
        config_paths=context.config_paths,
    )
    return _result(context, payload)


MODE_HANDLERS = {
    "cea": handle_cea,
    "nominal": handle_nominal,
    "oat": handle_oat,
    "corners": handle_corners,
    "geometry": handle_geometry,
    "internal_ballistics": handle_internal_ballistics,
    "injector_design": handle_injector_design,
    "hydraulic_predict": handle_hydraulic_predict,
    "hydraulic_calibrate": handle_hydraulic_calibrate,
    "hydraulic_compare": handle_hydraulic_compare,
    "structural_size": handle_structural_size,
    "thermal_size": handle_thermal_size,
    "nozzle_offdesign": handle_nozzle_offdesign,
    "cfd_plan": handle_cfd,
    "cfd_export_cases": handle_cfd,
    "cfd_ingest_results": handle_cfd,
    "cfd_apply_corrections": handle_cfd,
    "test_plan": handle_testing,
    "test_define_articles": handle_testing,
    "test_ingest_data": handle_testing,
    "test_compare_model": handle_testing,
    "test_calibrate_hotfire": handle_testing,
    "test_readiness": handle_testing,
}


def dispatch_workflow(context: WorkflowContext) -> dict[str, Any]:
    """Dispatch a prepared workflow context to its canonical mode handler."""

    LOGGER.info("Running workflow handler '%s' for run '%s'.", context.mode, context.run.run_id)
    result = MODE_HANDLERS[context.mode](context)
    LOGGER.info("Workflow handler '%s' completed for run '%s'.", context.mode, context.run.run_id)
    return result
