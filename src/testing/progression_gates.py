"""Progression-gate logic for staged test readiness."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from src.testing.test_types import HotfireCalibrationPackage, ModelVsTestComparison, ProgressionGateResult, TestRunSummary, TestStageDefinition


def _latest_stage_comparison(comparisons: Sequence[ModelVsTestComparison], stage_name: str) -> ModelVsTestComparison | None:
    matches = [comparison for comparison in comparisons if comparison.stage_name == stage_name]
    return matches[-1] if matches else None


def _stage_run_summaries(run_summaries: Sequence[TestRunSummary], stage_name: str) -> list[TestRunSummary]:
    return [summary for summary in run_summaries if summary.stage_name == stage_name]


def build_progression_gates(
    testing_config: Mapping[str, Any],
    *,
    stages: Sequence[TestStageDefinition],
    run_summaries: Sequence[TestRunSummary],
    comparisons: Sequence[ModelVsTestComparison],
    structural_result: Any | None,
    thermal_result: Any | None,
    nozzle_result: Any | None,
    hydraulic_calibration_ready: bool,
    cfd_context_available: bool,
    selected_calibration_package: HotfireCalibrationPackage | None,
) -> list[ProgressionGateResult]:
    """Evaluate explicit progression gates between campaign stages."""

    thresholds = dict(testing_config.get("progression_thresholds", {}))
    pressure_limit = float(thresholds.get("allowed_pressure_trace_error_percent", 15.0))
    thrust_limit = float(thresholds.get("allowed_thrust_trace_error_percent", 15.0))
    burn_limit = float(thresholds.get("allowed_burn_time_error_percent", 15.0))
    min_repeat_runs = int(thresholds.get("minimum_repeat_runs", 2))

    gates: list[ProgressionGateResult] = []
    for stage in stages:
        if stage.stage_name == "material_coupon":
            continue
        blocking_issues: list[str] = []
        criteria_results: dict[str, Any] = {}
        actions: list[str] = []
        if stage.stage_name == "hydraulic_validation":
            criteria_results["coupon_stage_defined"] = any(item.stage_name == "material_coupon" for item in stages)
            pass_fail = bool(criteria_results["coupon_stage_defined"])
            if not pass_fail:
                blocking_issues.append("Coupon/manufacturing stage is not defined in the active campaign.")
        elif stage.stage_name == "subscale_hotfire":
            criteria_results["hydraulic_calibration_ready"] = hydraulic_calibration_ready
            criteria_results["structural_baseline_nonblocking"] = bool(structural_result is None or structural_result.structural_valid)
            criteria_results["thermal_baseline_nonblocking"] = bool(thermal_result is None or thermal_result.thermal_valid)
            pass_fail = all(bool(value) for value in criteria_results.values())
            if not criteria_results["hydraulic_calibration_ready"]:
                blocking_issues.append("Cold-flow calibration is not complete enough to bound injector/feed behavior.")
            if not criteria_results["structural_baseline_nonblocking"]:
                blocking_issues.append("Structural sizing still has blocking validity failures.")
            if not criteria_results["thermal_baseline_nonblocking"]:
                blocking_issues.append("Thermal sizing still has blocking validity failures.")
        elif stage.stage_name == "fullscale_short_duration":
            comparison = _latest_stage_comparison(comparisons, "subscale_hotfire")
            criteria_results["subscale_hotfire_data_available"] = comparison is not None
            criteria_results["subscale_pressure_error_within_limit"] = bool(
                comparison
                and comparison.pressure_trace_error.get("available")
                and float(comparison.pressure_trace_error.get("rmse_percent", 1.0e9)) <= pressure_limit
            )
            criteria_results["subscale_thrust_error_within_limit"] = bool(
                comparison
                and comparison.thrust_trace_error.get("available")
                and float(comparison.thrust_trace_error.get("rmse_percent", 1.0e9)) <= thrust_limit
            )
            criteria_results["nozzle_ground_test_suitable"] = bool(
                nozzle_result is None or nozzle_result.recommendations.get("ground_test_suitable", True)
            )
            criteria_results["calibration_package_available"] = selected_calibration_package is not None
            criteria_results["cfd_context_satisfied"] = True if not bool(testing_config.get("require_cfd_before_fullscale", False)) else cfd_context_available
            pass_fail = all(bool(value) for value in criteria_results.values())
            if not criteria_results["subscale_hotfire_data_available"]:
                blocking_issues.append("No subscale hot-fire comparison is available.")
            if not criteria_results["subscale_pressure_error_within_limit"]:
                blocking_issues.append("Subscale chamber-pressure trace error remains above the configured limit.")
            if not criteria_results["subscale_thrust_error_within_limit"]:
                blocking_issues.append("Subscale thrust trace error remains above the configured limit.")
            if not criteria_results["nozzle_ground_test_suitable"]:
                blocking_issues.append("The current nozzle recommendation is too aggressive for ground-test use.")
            if not criteria_results["calibration_package_available"]:
                blocking_issues.append("No hot-fire calibration package is available from subscale data.")
            if not criteria_results["cfd_context_satisfied"]:
                blocking_issues.append("Configured full-scale progression requires CFD planning or corrections context, but none is available.")
        else:
            comparison = _latest_stage_comparison(comparisons, "fullscale_short_duration")
            short_runs = _stage_run_summaries(run_summaries, "fullscale_short_duration")
            criteria_results["fullscale_short_duration_data_available"] = bool(short_runs)
            criteria_results["fullscale_short_pressure_error_within_limit"] = bool(
                comparison
                and comparison.pressure_trace_error.get("available")
                and float(comparison.pressure_trace_error.get("rmse_percent", 1.0e9)) <= pressure_limit
            )
            criteria_results["fullscale_short_thrust_error_within_limit"] = bool(
                comparison
                and comparison.thrust_trace_error.get("available")
                and float(comparison.thrust_trace_error.get("rmse_percent", 1.0e9)) <= thrust_limit
            )
            criteria_results["fullscale_short_burn_time_within_limit"] = bool(
                comparison
                and comparison.burn_time_error.get("available")
                and abs(float(comparison.burn_time_error.get("delta_percent", 1.0e9))) <= burn_limit
            )
            criteria_results["thermal_baseline_nonblocking"] = bool(thermal_result is None or thermal_result.thermal_valid)
            criteria_results["short_duration_anomalies_absent"] = all(not summary.anomalies for summary in short_runs)
            criteria_results["repeatability_assessed_or_not_required"] = len(_stage_run_summaries(run_summaries, "fullscale_nominal_duration")) >= min_repeat_runs or len(_stage_run_summaries(run_summaries, "fullscale_nominal_duration")) == 0
            criteria_results["cfd_context_satisfied"] = True if not bool(testing_config.get("require_cfd_before_fullscale", False)) else cfd_context_available
            pass_fail = all(bool(value) for value in criteria_results.values())
            if not criteria_results["fullscale_short_duration_data_available"]:
                blocking_issues.append("No full-scale short-duration development run is available.")
            if not criteria_results["fullscale_short_pressure_error_within_limit"]:
                blocking_issues.append("Full-scale short-duration chamber-pressure error remains above the configured limit.")
            if not criteria_results["fullscale_short_thrust_error_within_limit"]:
                blocking_issues.append("Full-scale short-duration thrust error remains above the configured limit.")
            if not criteria_results["fullscale_short_burn_time_within_limit"]:
                blocking_issues.append("Full-scale short-duration burn-time error remains above the configured limit.")
            if not criteria_results["thermal_baseline_nonblocking"]:
                blocking_issues.append("Thermal baseline remains blocking for nominal-duration progression.")
            if not criteria_results["short_duration_anomalies_absent"]:
                blocking_issues.append("Full-scale short-duration anomalies need disposition before a nominal-duration run.")
            if not criteria_results["cfd_context_satisfied"]:
                blocking_issues.append("Configured nominal-duration progression requires CFD planning or corrections context, but none is available.")
        if blocking_issues:
            actions.extend(f"Resolve: {item}" for item in blocking_issues)
        else:
            actions.append(f"Proceed to {stage.stage_name}.")
        gates.append(
            ProgressionGateResult(
                stage_name=stage.stage_name,
                gate_name=f"ready_for_{stage.stage_name}",
                pass_fail=pass_fail,
                criteria_results=criteria_results,
                blocking_issues=blocking_issues,
                recommended_next_actions=actions,
                notes=["Decision gate uses explicit configured thresholds and available reduced-order comparison data."],
            )
        )
    return gates
