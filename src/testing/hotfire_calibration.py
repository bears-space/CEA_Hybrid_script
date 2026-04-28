"""Hot-fire calibration package generation and override application."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from src.testing.efficiency_fit import fit_efficiency_corrections
from src.testing.regression_fit import fit_regression_parameters
from src.testing.test_types import HotfireCalibrationPackage, ModelVsTestComparison, TestRunSummary
from src.testing.thermal_correlation import fit_thermal_multiplier


def _group_scale(stage_name: str) -> str:
    if "subscale" in stage_name:
        return "subscale"
    if "fullscale" in stage_name:
        return "fullscale"
    return "mixed"


def _filter_hotfire_items(
    summaries: Sequence[TestRunSummary],
    comparisons: Sequence[ModelVsTestComparison],
    source_mode: str,
) -> tuple[list[TestRunSummary], list[ModelVsTestComparison]]:
    def _allowed(stage_name: str) -> bool:
        if source_mode == "subscale_only":
            return "subscale" in stage_name
        if source_mode == "fullscale_only":
            return "fullscale" in stage_name
        return "hotfire" in stage_name or "fullscale" in stage_name

    return (
        [summary for summary in summaries if _allowed(summary.stage_name)],
        [comparison for comparison in comparisons if _allowed(comparison.stage_name)],
    )


def apply_hotfire_calibration_to_config(
    study_config: dict[str, Any],
    package: HotfireCalibrationPackage,
) -> dict[str, Any]:
    """Apply a selected hot-fire calibration package to copied config overrides."""

    updated = deepcopy(study_config)
    regression = dict(package.fitted_regression_parameters)
    if regression.get("a_reg_si") is not None:
        updated["nominal"]["blowdown"]["grain"]["a_reg_si"] = float(regression["a_reg_si"])
    if regression.get("n_reg") is not None:
        updated["nominal"]["blowdown"]["grain"]["n_reg"] = float(regression["n_reg"])
    if package.fitted_cstar_efficiency is not None:
        updated["nominal"]["loss_factors"]["cstar_efficiency"] = float(package.fitted_cstar_efficiency)
    if package.fitted_cf_or_nozzle_loss_correction is not None:
        updated["nominal"]["loss_factors"]["nozzle_discharge_factor"] = (
            float(updated["nominal"]["loss_factors"]["nozzle_discharge_factor"])
            * float(package.fitted_cf_or_nozzle_loss_correction)
        )
    if package.thermal_multiplier_correction is not None:
        updated["thermal"]["design_policy"]["throat_htc_multiplier"] = (
            float(updated["thermal"]["design_policy"]["throat_htc_multiplier"])
            * float(package.thermal_multiplier_correction)
        )
        updated["thermal"]["design_policy"]["injector_face_htc_multiplier"] = (
            float(updated["thermal"]["design_policy"]["injector_face_htc_multiplier"])
            * float(package.thermal_multiplier_correction)
        )
    updated.setdefault("testing", {})
    updated["testing"]["last_hotfire_calibration_package"] = package.to_dict()
    return updated


def build_hotfire_calibration_packages(
    testing_config: Mapping[str, Any],
    *,
    study_config: dict[str, Any],
    run_summaries: Sequence[TestRunSummary],
    comparisons: Sequence[ModelVsTestComparison],
) -> tuple[list[HotfireCalibrationPackage], HotfireCalibrationPackage | None, dict[str, Any] | None, list[str]]:
    """Build reusable hot-fire calibration packages from ingested hot-fire runs."""

    source_mode = str(testing_config.get("hotfire_corrections_source", "staged_combined")).lower()
    if source_mode == "none":
        return [], None, None, []
    selected_summaries, selected_comparisons = _filter_hotfire_items(run_summaries, comparisons, source_mode)
    if not selected_summaries or not selected_comparisons:
        return [], None, None, ["No usable hot-fire summaries and comparisons were available for calibration."]

    regression_parameters, regression_warnings = fit_regression_parameters(
        selected_summaries,
        selected_comparisons,
        nominal_a_reg_si=float(study_config["nominal"]["blowdown"]["grain"]["a_reg_si"]),
        nominal_n_reg=float(study_config["nominal"]["blowdown"]["grain"]["n_reg"]),
    )
    fitted_cstar, fitted_nozzle_loss, efficiency_warnings = fit_efficiency_corrections(
        selected_comparisons,
        nominal_cstar_efficiency=float(study_config["nominal"]["loss_factors"]["cstar_efficiency"]),
    )
    thermal_multiplier, thermal_warnings = fit_thermal_multiplier(selected_comparisons)
    ignition_times = [summary.ignition_time_s for summary in selected_summaries if summary.ignition_time_s is not None]
    ignition_delay = None if not ignition_times else float(sum(ignition_times) / len(ignition_times))
    source_scales = {_group_scale(summary.stage_name) for summary in selected_summaries}
    source_scale = source_scales.pop() if len(source_scales) == 1 else "mixed"
    package = HotfireCalibrationPackage(
        package_name=f"hotfire_{source_mode}",
        source_run_ids=[summary.run_id for summary in selected_summaries],
        source_scale=source_scale,
        transferability="tentative_subscale_transfer" if source_scale == "subscale" else "direct_fullscale_reuse" if source_scale == "fullscale" else "mixed_staged_transfer",
        fitted_regression_parameters=regression_parameters,
        fitted_cstar_efficiency=fitted_cstar,
        fitted_cf_or_nozzle_loss_correction=fitted_nozzle_loss,
        ignition_delay_correction=ignition_delay,
        thermal_multiplier_correction=thermal_multiplier,
        valid_operating_range={
            "stage_names": sorted({summary.stage_name for summary in selected_summaries}),
            "run_count": len(selected_summaries),
            "max_pressure_pa": max(summary.peak_chamber_pressure_pa or 0.0 for summary in selected_summaries),
            "max_burn_time_s": max(summary.achieved_burn_time_s for summary in selected_summaries),
        },
        confidence_level="medium" if len(selected_summaries) >= 2 else "low",
        notes=[
            *regression_warnings,
            *efficiency_warnings,
            *thermal_warnings,
            "Calibration package is explicit and optional; it does not silently overwrite the nominal reduced-order model.",
        ],
    )
    updated_config = apply_hotfire_calibration_to_config(study_config, package)
    package = HotfireCalibrationPackage(
        package_name=package.package_name,
        source_run_ids=package.source_run_ids,
        source_scale=package.source_scale,
        transferability=package.transferability,
        fitted_regression_parameters=package.fitted_regression_parameters,
        fitted_cstar_efficiency=package.fitted_cstar_efficiency,
        fitted_cf_or_nozzle_loss_correction=package.fitted_cf_or_nozzle_loss_correction,
        ignition_delay_correction=package.ignition_delay_correction,
        thermal_multiplier_correction=package.thermal_multiplier_correction,
        valid_operating_range=package.valid_operating_range,
        confidence_level=package.confidence_level,
        downstream_overrides=updated_config,
        notes=package.notes,
    )
    return [package], package, updated_config, []
