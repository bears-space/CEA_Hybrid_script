"""Joint feed and injector calibration with identifiability checks."""

from __future__ import annotations

from typing import Any, Mapping

from src.hydraulic_validation.coldflow_types import ColdFlowDataset, JointCalibrationResult
from src.hydraulic_validation.feed_calibration import calibrate_feed_model
from src.hydraulic_validation.hydraulic_predictor import HydraulicModelContext, apply_parameter_updates_to_context, predict_dataset
from src.hydraulic_validation.injector_calibration import calibrate_injector_model
from src.hydraulic_validation.residuals import build_residuals, residual_statistics
from src.hydraulic_validation.validation_checks import evaluate_calibration_credibility, observation_flags


def calibrate_joint_model(
    dataset: ColdFlowDataset,
    context: HydraulicModelContext,
    coldflow_config: Mapping[str, Any],
) -> JointCalibrationResult:
    """Fit feed loss and injector CdA together when the dataset supports separation."""

    flags = observation_flags(dataset)
    warnings: list[str] = []
    if not flags["joint_identifiable"]:
        warnings.append(
            "Joint calibration requires at least one feed observation and one injector observation."
        )
        return JointCalibrationResult(
            calibration_mode="joint",
            base_model_source=context.base_model_source,
            calibration_fluid=str(coldflow_config.get("fluid", {}).get("name", "unspecified")),
            data_points_used=0,
            feed_loss_multiplier=1.0,
            feed_pressure_drop_multiplier_calibrated=float(context.feed_config.pressure_drop_multiplier),
            equivalent_total_loss_factor_calibrated=float(context.feed_config.minor_loss_k_total)
            + float(context.feed_config.friction_factor) * float(context.feed_config.line_length_m / context.feed_config.line_id_m),
            injector_cd_calibrated=float(context.injector_config.cd),
            injector_effective_cda_calibrated_m2=float(context.injector_config.cd) * float(context.injector_config.total_area_m2),
            injector_cda_multiplier=1.0,
            geometry_backcalc_correction_factor=(
                1.0 if context.base_model_source == "geometry_backcalculated" else None
            ),
            residual_statistics={},
            validation_flags=flags,
            calibration_valid=False,
            warnings=warnings,
            failure_reason="joint_calibration_underdetermined",
        )

    feed_result = calibrate_feed_model(dataset, context, coldflow_config)
    injector_result = calibrate_injector_model(dataset, context, coldflow_config)
    calibrated_context = apply_parameter_updates_to_context(
        context,
        {
            "feed_pressure_drop_multiplier_calibrated": feed_result.feed_pressure_drop_multiplier_calibrated,
            "injector_cda_multiplier": injector_result.injector_cda_multiplier,
            "geometry_backcalc_correction_factor": injector_result.geometry_backcalc_correction_factor,
        },
        hydraulic_source=(
            "geometry_plus_coldflow"
            if context.base_model_source == "geometry_backcalculated"
            else "coldflow_calibrated"
        ),
    )
    calibrated_predictions = predict_dataset(dataset, calibrated_context, coldflow_config)
    calibrated_residuals = build_residuals(dataset, calibrated_predictions)
    stats = residual_statistics(dataset, calibrated_residuals)
    fitted_parameters = {
        "feed_loss_multiplier": feed_result.feed_loss_multiplier,
        "feed_pressure_drop_multiplier_calibrated": feed_result.feed_pressure_drop_multiplier_calibrated,
        "equivalent_total_loss_factor_calibrated": feed_result.equivalent_total_loss_factor_calibrated,
        "injector_cd_calibrated": injector_result.injector_cd_calibrated,
        "injector_effective_cda_calibrated_m2": injector_result.injector_effective_cda_calibrated_m2,
        "injector_cda_multiplier": injector_result.injector_cda_multiplier,
        "geometry_backcalc_correction_factor": injector_result.geometry_backcalc_correction_factor,
    }
    flags, credibility_warnings, calibration_valid, failure_reason = evaluate_calibration_credibility(
        calibration_mode="joint",
        dataset=dataset,
        residual_statistics=stats,
        fitted_parameters=fitted_parameters,
        design_reference=context.design_reference,
        surrogate_fluid_used=bool(dataset.rig_definition.surrogate_fluid_used),
    )
    warnings.extend(feed_result.warnings)
    warnings.extend(injector_result.warnings)
    warnings.extend(credibility_warnings)
    return JointCalibrationResult(
        calibration_mode="joint",
        base_model_source=context.base_model_source,
        calibration_fluid=str(coldflow_config.get("fluid", {}).get("name", "unspecified")),
        data_points_used=min(feed_result.data_points_used, injector_result.data_points_used),
        feed_loss_multiplier=feed_result.feed_loss_multiplier,
        feed_pressure_drop_multiplier_calibrated=feed_result.feed_pressure_drop_multiplier_calibrated,
        equivalent_total_loss_factor_calibrated=feed_result.equivalent_total_loss_factor_calibrated,
        injector_cd_calibrated=injector_result.injector_cd_calibrated,
        injector_effective_cda_calibrated_m2=injector_result.injector_effective_cda_calibrated_m2,
        injector_cda_multiplier=injector_result.injector_cda_multiplier,
        geometry_backcalc_correction_factor=injector_result.geometry_backcalc_correction_factor,
        residual_statistics=stats,
        validation_flags=flags,
        calibration_valid=calibration_valid and feed_result.calibration_valid and injector_result.calibration_valid,
        warnings=warnings,
        failure_reason=failure_reason,
        feed_result=feed_result,
        injector_result=injector_result,
    )
