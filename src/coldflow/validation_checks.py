"""Validation and credibility checks for Step 5 cold-flow calibration."""

from __future__ import annotations

from typing import Any, Mapping

from src.coldflow.coldflow_types import ColdFlowDataset
from src.coldflow.residuals import measured_feed_delta_p_pa, measured_injector_delta_p_pa


def observation_flags(dataset: ColdFlowDataset) -> dict[str, bool]:
    """Return the measurement observability flags that drive calibration identifiability."""

    point_count = len(dataset.points)
    has_feed_observation = any(measured_feed_delta_p_pa(point) is not None for point in dataset.points)
    has_injector_observation = any(measured_injector_delta_p_pa(point) is not None for point in dataset.points)
    has_inlet_tap = any(point.injector_inlet_pressure_pa is not None for point in dataset.points)
    has_upstream = any(point.upstream_pressure_pa is not None for point in dataset.points)
    return {
        "has_points": point_count > 0,
        "has_multiple_points": point_count >= 2,
        "has_feed_observation": has_feed_observation,
        "has_injector_observation": has_injector_observation,
        "has_inlet_tap": has_inlet_tap,
        "has_upstream_pressure": has_upstream,
        "joint_identifiable": has_feed_observation and has_injector_observation,
    }


def pressure_range_warnings(
    dataset: ColdFlowDataset,
    design_reference: Mapping[str, float],
) -> list[str]:
    """Warn when the dataset does not cover the engine design-point pressure regime."""

    warnings: list[str] = []
    injector_dp_values = [measured_injector_delta_p_pa(point) for point in dataset.points]
    injector_dp_values = [float(value) for value in injector_dp_values if value is not None]
    if injector_dp_values:
        design_dp_inj = float(design_reference.get("design_injector_delta_p_pa", 0.0))
        if design_dp_inj > max(injector_dp_values) * 1.25 or design_dp_inj < min(injector_dp_values) * 0.75:
            warnings.append(
                "Cold-flow injector delta-p range does not bracket the nominal engine design point; transfer to hot-fire should be treated cautiously."
            )
    feed_dp_values = [measured_feed_delta_p_pa(point) for point in dataset.points]
    feed_dp_values = [float(value) for value in feed_dp_values if value is not None]
    if feed_dp_values:
        design_dp_feed = float(design_reference.get("design_feed_delta_p_pa", 0.0))
        if design_dp_feed > max(feed_dp_values) * 1.25 or design_dp_feed < min(feed_dp_values) * 0.75:
            warnings.append(
                "Cold-flow feed delta-p range does not bracket the nominal engine design point."
            )
    return warnings


def evaluate_calibration_credibility(
    *,
    calibration_mode: str,
    dataset: ColdFlowDataset,
    residual_statistics: Mapping[str, Any],
    fitted_parameters: Mapping[str, Any],
    design_reference: Mapping[str, float],
    surrogate_fluid_used: bool,
) -> tuple[dict[str, bool], list[str], bool, str | None]:
    """Return credibility flags, warnings, and an overall validity decision."""

    flags = observation_flags(dataset)
    warnings = pressure_range_warnings(dataset, design_reference)
    if surrogate_fluid_used:
        warnings.append(
            "This calibration package is tagged as surrogate-fluid only; use it for hydraulic shakedown, not direct N2O truth."
        )

    if calibration_mode == "joint" and not flags["joint_identifiable"]:
        warnings.append(
            "Joint calibration is underdetermined without separate feed and injector pressure observations."
        )
        return flags, warnings, False, "joint_calibration_underdetermined"

    mdot_percent_rmse = residual_statistics.get("mdot_error_percent", {}).get("rmse")
    if mdot_percent_rmse is not None and float(mdot_percent_rmse) > 10.0:
        warnings.append(
            f"Calibrated mass-flow RMSE remains high at {float(mdot_percent_rmse):.2f}%."
        )

    feed_multiplier = fitted_parameters.get("feed_loss_multiplier")
    if feed_multiplier is not None and (float(feed_multiplier) <= 0.0 or float(feed_multiplier) > 10.0):
        warnings.append("Fitted feed-loss multiplier is outside the credible range (0, 10].")
        return flags, warnings, False, "feed_multiplier_out_of_bounds"

    injector_cd = fitted_parameters.get("injector_cd_calibrated")
    if injector_cd is not None and (float(injector_cd) <= 0.05 or float(injector_cd) > 1.1):
        warnings.append("Fitted injector Cd is outside the credible range (0.05, 1.1].")
        return flags, warnings, False, "injector_cd_out_of_bounds"

    geometry_factor = fitted_parameters.get("geometry_backcalc_correction_factor")
    if geometry_factor is not None and (float(geometry_factor) <= 0.1 or float(geometry_factor) > 3.0):
        warnings.append("Geometry-backed injector correction factor is outside the credible range (0.1, 3].")
        return flags, warnings, False, "geometry_backcalc_factor_out_of_bounds"

    valid = True
    failure_reason = None
    if mdot_percent_rmse is not None and float(mdot_percent_rmse) > 20.0:
        valid = False
        failure_reason = "residuals_remain_large_after_calibration"
    return flags, warnings, valid, failure_reason
