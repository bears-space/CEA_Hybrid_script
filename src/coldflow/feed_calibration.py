"""Feed-system calibration against cold-flow rig data."""

from __future__ import annotations

from typing import Any, Mapping

from blowdown_hybrid.hydraulics import feed_pressure_drop_pa

from src.coldflow.coldflow_types import ColdFlowDataset, FeedCalibrationResult
from src.coldflow.hydraulic_predictor import HydraulicModelContext, apply_parameter_updates_to_context, injector_delta_p_from_mdot, predict_dataset
from src.coldflow.residuals import build_residuals, measured_feed_delta_p_pa, residual_statistics
from src.coldflow.surrogate_fluid import resolve_point_density_kg_m3
from src.coldflow.validation_checks import evaluate_calibration_credibility


def _observed_feed_delta_p_pa(
    point,
    context: HydraulicModelContext,
    coldflow_config: Mapping[str, Any],
) -> float | None:
    explicit_feed_delta_p_pa = measured_feed_delta_p_pa(point)
    if explicit_feed_delta_p_pa is not None:
        return explicit_feed_delta_p_pa
    if point.upstream_pressure_pa is None or point.downstream_pressure_pa is None or point.measured_mdot_kg_s is None:
        return None
    density_kg_m3 = resolve_point_density_kg_m3(point, coldflow_config)
    injector_delta_p_pa = injector_delta_p_from_mdot(
        float(point.measured_mdot_kg_s),
        density_kg_m3,
        context.injector_config,
    )
    return float(point.upstream_pressure_pa) - float(point.downstream_pressure_pa) - injector_delta_p_pa


def calibrate_feed_model(
    dataset: ColdFlowDataset,
    context: HydraulicModelContext,
    coldflow_config: Mapping[str, Any],
) -> FeedCalibrationResult:
    """Fit a scalar feed-loss multiplier against measured or inferred feed delta-p."""

    numerator = 0.0
    denominator = 0.0
    points_used = 0
    warnings: list[str] = []

    for point in dataset.points:
        if point.measured_mdot_kg_s is None:
            continue
        density_kg_m3 = resolve_point_density_kg_m3(point, coldflow_config)
        observed_feed_delta_p_pa = _observed_feed_delta_p_pa(point, context, coldflow_config)
        if observed_feed_delta_p_pa is None or observed_feed_delta_p_pa <= 0.0:
            continue
        base_feed_delta_p_pa = feed_pressure_drop_pa(
            float(point.measured_mdot_kg_s),
            density_kg_m3,
            context.feed_config,
        )
        if base_feed_delta_p_pa <= 0.0:
            continue
        numerator += base_feed_delta_p_pa * observed_feed_delta_p_pa
        denominator += base_feed_delta_p_pa**2
        points_used += 1

    if points_used == 0 or denominator <= 0.0:
        return FeedCalibrationResult(
            calibration_mode="feed_only",
            calibration_fluid=str(coldflow_config.get("fluid", {}).get("name", "unspecified")),
            data_points_used=points_used,
            feed_loss_multiplier=1.0,
            feed_pressure_drop_multiplier_calibrated=float(context.feed_config.pressure_drop_multiplier),
            equivalent_total_loss_factor_calibrated=float(context.feed_config.minor_loss_k_total)
            + float(context.feed_config.friction_factor) * float(context.feed_config.line_length_m / context.feed_config.line_id_m),
            residual_statistics={},
            validation_flags={},
            calibration_valid=False,
            warnings=["Feed calibration requires at least one point with feed delta-p or enough pressure data to infer it."],
            failure_reason="insufficient_feed_observations",
        )

    feed_loss_multiplier = max(numerator / denominator, 1.0e-6)
    feed_pressure_drop_multiplier_calibrated = float(context.feed_config.pressure_drop_multiplier) * feed_loss_multiplier
    effective_loss_factor = (
        float(context.feed_config.minor_loss_k_total)
        + float(context.feed_config.friction_factor) * float(context.feed_config.line_length_m / context.feed_config.line_id_m)
    ) * feed_pressure_drop_multiplier_calibrated
    calibrated_context = apply_parameter_updates_to_context(
        context,
        {"feed_pressure_drop_multiplier_calibrated": feed_pressure_drop_multiplier_calibrated},
        hydraulic_source="coldflow_calibrated",
    )
    calibrated_predictions = predict_dataset(dataset, calibrated_context, coldflow_config)
    calibrated_residuals = build_residuals(dataset, calibrated_predictions)
    stats = residual_statistics(dataset, calibrated_residuals)
    fitted_parameters = {
        "feed_loss_multiplier": feed_loss_multiplier,
        "feed_pressure_drop_multiplier_calibrated": feed_pressure_drop_multiplier_calibrated,
        "equivalent_total_loss_factor_calibrated": effective_loss_factor,
    }
    flags, credibility_warnings, calibration_valid, failure_reason = evaluate_calibration_credibility(
        calibration_mode="feed_only",
        dataset=dataset,
        residual_statistics=stats,
        fitted_parameters=fitted_parameters,
        design_reference=context.design_reference,
        surrogate_fluid_used=bool(dataset.rig_definition.surrogate_fluid_used),
    )
    warnings.extend(credibility_warnings)
    return FeedCalibrationResult(
        calibration_mode="feed_only",
        calibration_fluid=str(coldflow_config.get("fluid", {}).get("name", "unspecified")),
        data_points_used=points_used,
        feed_loss_multiplier=feed_loss_multiplier,
        feed_pressure_drop_multiplier_calibrated=feed_pressure_drop_multiplier_calibrated,
        equivalent_total_loss_factor_calibrated=effective_loss_factor,
        residual_statistics=stats,
        validation_flags=flags,
        calibration_valid=calibration_valid,
        warnings=warnings,
        failure_reason=failure_reason,
    )
