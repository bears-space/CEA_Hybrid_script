"""Injector-only calibration against measured cold-flow data."""

from __future__ import annotations

from typing import Any, Mapping

from src.hydraulic_validation.coldflow_types import ColdFlowDataset, InjectorCalibrationResult
from src.hydraulic_validation.hydraulic_predictor import (
    HydraulicModelContext,
    apply_parameter_updates_to_context,
    injector_effective_cda_m2,
    predict_dataset,
)
from src.hydraulic_validation.residuals import build_residuals, measured_injector_delta_p_pa, residual_statistics
from src.hydraulic_validation.surrogate_fluid import resolve_point_density_kg_m3
from src.hydraulic_validation.validation_checks import evaluate_calibration_credibility


def _mdot_weight(point_uncertainty: Mapping[str, float]) -> float:
    mdot_sigma = point_uncertainty.get("measured_mdot_kg_s")
    if mdot_sigma is None or float(mdot_sigma) <= 0.0:
        return 1.0
    return 1.0 / float(mdot_sigma) ** 2


def calibrate_injector_model(
    dataset: ColdFlowDataset,
    context: HydraulicModelContext,
    coldflow_config: Mapping[str, Any],
) -> InjectorCalibrationResult:
    """Fit a scalar injector CdA correction against injector-pressure observations."""

    base_cda_m2 = injector_effective_cda_m2(context.injector_config)
    numerator = 0.0
    denominator = 0.0
    points_used = 0
    warnings: list[str] = []

    for point in dataset.points:
        injector_delta_p_pa = measured_injector_delta_p_pa(point)
        if injector_delta_p_pa is None or injector_delta_p_pa <= 0.0 or point.measured_mdot_kg_s is None:
            continue
        density_kg_m3 = resolve_point_density_kg_m3(point, coldflow_config)
        term = base_cda_m2 * (2.0 * density_kg_m3 * injector_delta_p_pa) ** 0.5
        weight = _mdot_weight(point.measurement_uncertainty)
        numerator += weight * term * float(point.measured_mdot_kg_s)
        denominator += weight * term**2
        points_used += 1

    if points_used == 0 or denominator <= 0.0:
        return InjectorCalibrationResult(
            calibration_mode="injector_only",
            base_model_source=context.base_model_source,
            calibration_fluid=str(coldflow_config.get("fluid", {}).get("name", "unspecified")),
            data_points_used=points_used,
            injector_cd_calibrated=float(context.injector_config.cd),
            injector_effective_cda_calibrated_m2=base_cda_m2,
            injector_cda_multiplier=1.0,
            geometry_backcalc_correction_factor=(
                1.0 if context.base_model_source == "geometry_backcalculated" else None
            ),
            residual_statistics={},
            validation_flags={},
            calibration_valid=False,
            warnings=["Injector calibration requires at least one point with injector delta-p and measured mass flow."],
            failure_reason="insufficient_injector_observations",
        )

    injector_cda_multiplier = max(numerator / denominator, 1.0e-6)
    injector_cd_calibrated = float(context.injector_config.cd) * injector_cda_multiplier
    calibrated_context = apply_parameter_updates_to_context(
        context,
        {"injector_cda_multiplier": injector_cda_multiplier},
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
        "injector_cd_calibrated": injector_cd_calibrated,
        "injector_effective_cda_calibrated_m2": base_cda_m2 * injector_cda_multiplier,
        "injector_cda_multiplier": injector_cda_multiplier,
        "geometry_backcalc_correction_factor": (
            injector_cda_multiplier if context.base_model_source == "geometry_backcalculated" else None
        ),
    }
    flags, credibility_warnings, calibration_valid, failure_reason = evaluate_calibration_credibility(
        calibration_mode="injector_only",
        dataset=dataset,
        residual_statistics=stats,
        fitted_parameters=fitted_parameters,
        design_reference=context.design_reference,
        surrogate_fluid_used=bool(dataset.rig_definition.surrogate_fluid_used),
    )
    warnings.extend(credibility_warnings)
    return InjectorCalibrationResult(
        calibration_mode="injector_only",
        base_model_source=context.base_model_source,
        calibration_fluid=str(coldflow_config.get("fluid", {}).get("name", "unspecified")),
        data_points_used=points_used,
        injector_cd_calibrated=injector_cd_calibrated,
        injector_effective_cda_calibrated_m2=base_cda_m2 * injector_cda_multiplier,
        injector_cda_multiplier=injector_cda_multiplier,
        geometry_backcalc_correction_factor=(
            injector_cda_multiplier if context.base_model_source == "geometry_backcalculated" else None
        ),
        residual_statistics=stats,
        validation_flags=flags,
        calibration_valid=calibration_valid,
        warnings=warnings,
        failure_reason=failure_reason,
    )
