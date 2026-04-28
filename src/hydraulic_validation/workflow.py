"""High-level hydraulic validation workflow orchestration."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from src.hydraulic_validation.calibration_store import load_calibration_package
from src.hydraulic_validation.coldflow_export import write_coldflow_outputs
from src.hydraulic_validation.coldflow_types import (
    CalibrationPackage,
    FeedCalibrationResult,
    InjectorCalibrationResult,
    JointCalibrationResult,
)
from src.hydraulic_validation.data_ingest import load_coldflow_dataset
from src.hydraulic_validation.feed_calibration import calibrate_feed_model
from src.hydraulic_validation.hydraulic_predictor import apply_parameter_updates_to_context, build_prediction_context, predict_dataset
from src.hydraulic_validation.injector_calibration import calibrate_injector_model
from src.hydraulic_validation.joint_calibration import calibrate_joint_model
from src.hydraulic_validation.residuals import build_residuals, prediction_rows, residual_rows, residual_statistics
from src.hydraulic_validation.surrogate_fluid import surrogate_fluid_warnings
from src.io_utils import deep_merge


def build_calibration_package(
    *,
    dataset,
    coldflow_config: Mapping[str, Any],
    context,
    calibration_result: FeedCalibrationResult | InjectorCalibrationResult | JointCalibrationResult,
) -> CalibrationPackage:
    """Build the reusable calibration package exported by the hydraulic-validation workflow."""

    surrogate_fluid_used = bool(dataset.rig_definition.surrogate_fluid_used or coldflow_config.get("fluid", {}).get("is_surrogate", False))
    if isinstance(calibration_result, JointCalibrationResult):
        recommended_model_source = (
            "geometry_plus_coldflow"
            if calibration_result.base_model_source == "geometry_backcalculated"
            else "coldflow_calibrated"
        )
        fitted_parameters = {
            "feed_loss_multiplier": calibration_result.feed_loss_multiplier,
            "feed_pressure_drop_multiplier_calibrated": calibration_result.feed_pressure_drop_multiplier_calibrated,
            "equivalent_total_loss_factor_calibrated": calibration_result.equivalent_total_loss_factor_calibrated,
            "injector_cd_calibrated": calibration_result.injector_cd_calibrated,
            "injector_effective_cda_calibrated_m2": calibration_result.injector_effective_cda_calibrated_m2,
            "injector_cda_multiplier": calibration_result.injector_cda_multiplier,
            "geometry_backcalc_correction_factor": calibration_result.geometry_backcalc_correction_factor,
        }
        feed_result = calibration_result.feed_result
        injector_result = calibration_result.injector_result
        joint_result = calibration_result
    elif isinstance(calibration_result, FeedCalibrationResult):
        recommended_model_source = "coldflow_calibrated"
        fitted_parameters = {
            "feed_loss_multiplier": calibration_result.feed_loss_multiplier,
            "feed_pressure_drop_multiplier_calibrated": calibration_result.feed_pressure_drop_multiplier_calibrated,
            "equivalent_total_loss_factor_calibrated": calibration_result.equivalent_total_loss_factor_calibrated,
        }
        feed_result = calibration_result
        injector_result = None
        joint_result = None
    else:
        recommended_model_source = (
            "geometry_plus_coldflow"
            if calibration_result.base_model_source == "geometry_backcalculated"
            else "coldflow_calibrated"
        )
        fitted_parameters = {
            "injector_cd_calibrated": calibration_result.injector_cd_calibrated,
            "injector_effective_cda_calibrated_m2": calibration_result.injector_effective_cda_calibrated_m2,
            "injector_cda_multiplier": calibration_result.injector_cda_multiplier,
            "geometry_backcalc_correction_factor": calibration_result.geometry_backcalc_correction_factor,
        }
        feed_result = None
        injector_result = calibration_result
        joint_result = None

    warnings = [*dataset.warnings, *surrogate_fluid_warnings(dataset, coldflow_config), *calibration_result.warnings]
    return CalibrationPackage(
        calibration_mode=calibration_result.calibration_mode,
        hydraulic_source=str(coldflow_config.get("hydraulic_source", "nominal_uncalibrated")),
        recommended_model_source=recommended_model_source,
        calibration_fluid=str(coldflow_config.get("fluid", {}).get("name", "unspecified")),
        surrogate_fluid_used=surrogate_fluid_used,
        intended_application=str(coldflow_config.get("fluid", {}).get("intended_application", "general hydraulic validation")),
        fitted_parameters=fitted_parameters,
        residual_statistics=dict(calibration_result.residual_statistics),
        validity_flags=dict(calibration_result.validation_flags),
        calibration_valid=bool(calibration_result.calibration_valid),
        warnings=warnings,
        failure_reason=calibration_result.failure_reason,
        reference_dataset_metadata={
            "dataset_name": dataset.dataset_name,
            "test_mode": dataset.test_mode,
            "point_count": len(dataset.points),
            "source_path": dataset.metadata.get("source_path"),
            "base_model_source": context.base_model_source,
        },
        recommended_parameter_updates=fitted_parameters,
        feed_result=feed_result,
        injector_result=injector_result,
        joint_result=joint_result,
    )


def _baseline_context(study_config: Mapping[str, Any], coldflow_config: Mapping[str, Any]):
    uncalibrated_config = deepcopy(dict(study_config))
    uncalibrated_config.setdefault("hydraulic_validation", {})["hydraulic_source"] = "nominal_uncalibrated"
    return build_prediction_context(uncalibrated_config, coldflow_config)


def _load_and_predict(
    study_config: Mapping[str, Any],
    coldflow_config: Mapping[str, Any],
):
    dataset = load_coldflow_dataset(coldflow_config["dataset_path"], coldflow_config)
    context = _baseline_context(study_config, coldflow_config)
    baseline_predictions = predict_dataset(dataset, context, coldflow_config)
    baseline_residuals = build_residuals(dataset, baseline_predictions)
    baseline_stats = residual_statistics(dataset, baseline_residuals)
    return dataset, context, baseline_predictions, baseline_residuals, baseline_stats


def run_coldflow_prediction_workflow(
    study_config: Mapping[str, Any],
    coldflow_config: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Run prediction-only comparison against a cold-flow dataset."""

    dataset, context, baseline_predictions, baseline_residuals, baseline_stats = _load_and_predict(study_config, coldflow_config)
    destination = write_coldflow_outputs(
        output_dir,
        dataset=dataset,
        coldflow_config={**coldflow_config, "calibration_mode": "predict_only"},
        baseline_predictions=prediction_rows(baseline_predictions, comparison_label="baseline"),
        baseline_residuals=residual_rows(baseline_residuals, comparison_label="baseline"),
        baseline_stats=baseline_stats,
    )
    return {
        "output_dir": destination,
        "dataset": dataset,
        "context": context,
        "baseline_stats": baseline_stats,
    }


def run_coldflow_calibration_workflow(
    study_config: Mapping[str, Any],
    coldflow_config: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Run calibration and export a reusable hydraulic-validation package."""

    dataset, context, baseline_predictions, baseline_residuals, baseline_stats = _load_and_predict(study_config, coldflow_config)
    calibration_mode = str(coldflow_config.get("calibration_mode", "joint")).lower()
    if calibration_mode == "injector_only":
        calibration_result = calibrate_injector_model(dataset, context, coldflow_config)
    elif calibration_mode == "feed_only":
        calibration_result = calibrate_feed_model(dataset, context, coldflow_config)
    elif calibration_mode == "joint":
        calibration_result = calibrate_joint_model(dataset, context, coldflow_config)
    else:
        raise ValueError(f"Unsupported cold-flow calibration mode: {calibration_mode}")

    calibration_package = build_calibration_package(
        dataset=dataset,
        coldflow_config=coldflow_config,
        context=context,
        calibration_result=calibration_result,
    )
    calibrated_context = apply_parameter_updates_to_context(
        context,
        calibration_package.recommended_parameter_updates,
        hydraulic_source=calibration_package.recommended_model_source,
    )
    calibrated_predictions = predict_dataset(dataset, calibrated_context, coldflow_config)
    calibrated_residuals = build_residuals(dataset, calibrated_predictions)
    calibrated_stats = residual_statistics(dataset, calibrated_residuals)
    destination = write_coldflow_outputs(
        output_dir,
        dataset=dataset,
        coldflow_config=coldflow_config,
        baseline_predictions=prediction_rows(baseline_predictions, comparison_label="baseline"),
        baseline_residuals=residual_rows(baseline_residuals, comparison_label="baseline"),
        baseline_stats=baseline_stats,
        calibrated_predictions=prediction_rows(calibrated_predictions, comparison_label="calibrated"),
        calibrated_residuals=residual_rows(calibrated_residuals, comparison_label="calibrated"),
        calibrated_stats=calibrated_stats,
        injector_result=calibration_package.injector_result,
        feed_result=calibration_package.feed_result,
        joint_result=calibration_package.joint_result,
        calibration_package=calibration_package,
    )
    return {
        "output_dir": destination,
        "dataset": dataset,
        "context": context,
        "baseline_stats": baseline_stats,
        "calibrated_stats": calibrated_stats,
        "calibration_package": calibration_package,
    }


def run_coldflow_compare_workflow(
    study_config: Mapping[str, Any],
    coldflow_config: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Compare baseline and an existing calibration package against a cold-flow dataset."""

    dataset, context, baseline_predictions, baseline_residuals, baseline_stats = _load_and_predict(study_config, coldflow_config)
    calibration_path = (
        str(coldflow_config.get("comparison_package_path", "")).strip()
        or str(coldflow_config.get("calibration_package_path", "")).strip()
    )
    if not calibration_path:
        raise ValueError("coldflow.compare requires comparison_package_path or calibration_package_path.")
    calibration_package = load_calibration_package(calibration_path)
    calibrated_context = apply_parameter_updates_to_context(
        context,
        calibration_package.recommended_parameter_updates,
        hydraulic_source=calibration_package.recommended_model_source,
    )
    calibrated_predictions = predict_dataset(dataset, calibrated_context, coldflow_config)
    calibrated_residuals = build_residuals(dataset, calibrated_predictions)
    calibrated_stats = residual_statistics(dataset, calibrated_residuals)
    destination = write_coldflow_outputs(
        output_dir,
        dataset=dataset,
        coldflow_config={**coldflow_config, "calibration_mode": calibration_package.calibration_mode},
        baseline_predictions=prediction_rows(baseline_predictions, comparison_label="baseline"),
        baseline_residuals=residual_rows(baseline_residuals, comparison_label="baseline"),
        baseline_stats=baseline_stats,
        calibrated_predictions=prediction_rows(calibrated_predictions, comparison_label="calibrated"),
        calibrated_residuals=residual_rows(calibrated_residuals, comparison_label="calibrated"),
        calibrated_stats=calibrated_stats,
        injector_result=calibration_package.injector_result,
        feed_result=calibration_package.feed_result,
        joint_result=calibration_package.joint_result,
        calibration_package=calibration_package,
    )
    return {
        "output_dir": destination,
        "dataset": dataset,
        "context": context,
        "baseline_stats": baseline_stats,
        "calibrated_stats": calibrated_stats,
        "calibration_package": calibration_package,
    }


def merge_coldflow_config(study_config: Mapping[str, Any], override: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the normalized cold-flow config section after applying overrides."""

    override_section = dict(override or {})
    if "coldflow" in override_section and isinstance(override_section["coldflow"], Mapping):
        override_section = dict(override_section["coldflow"])
    return deep_merge(dict(study_config.get("coldflow", {})), override_section)


def merge_hydraulic_validation_config(
    study_config: Mapping[str, Any],
    override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the normalized hydraulic-validation config section after applying overrides."""

    override_section = dict(override or {})
    if "hydraulic_validation" in override_section and isinstance(override_section["hydraulic_validation"], Mapping):
        override_section = dict(override_section["hydraulic_validation"])
    elif "coldflow" in override_section and isinstance(override_section["coldflow"], Mapping):
        override_section = dict(override_section["coldflow"])
    return deep_merge(dict(study_config.get("hydraulic_validation", study_config.get("coldflow", {}))), override_section)


run_hydraulic_prediction_workflow = run_coldflow_prediction_workflow
run_hydraulic_calibration_workflow = run_coldflow_calibration_workflow
run_hydraulic_compare_workflow = run_coldflow_compare_workflow
