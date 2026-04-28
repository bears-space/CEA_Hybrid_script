"""Compare reduced-order solver outputs against measured test traces."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from src.testing.test_types import ModelVsTestComparison, TestDataset, TestRunSummary


def select_model_history(
    testing_config: Mapping[str, Any],
    *,
    nominal_payload: Mapping[str, Any],
    ballistics_payload: Mapping[str, Any] | None = None,
) -> tuple[str, Mapping[str, Any], Mapping[str, Any]]:
    """Select the reduced-order source for model-vs-test comparison."""

    source = str(testing_config.get("model_vs_test_source", "0d")).lower()
    if source in {"1d", "transient_1d"} and ballistics_payload is not None and ballistics_payload.get("result", {}).get("history"):
        return "1d", ballistics_payload["result"]["history"], ballistics_payload.get("metrics", {})
    return "0d", nominal_payload.get("result", {}).get("history", {}), nominal_payload.get("metrics", {})


def _trace_error(model_time: np.ndarray, model_values: np.ndarray, test_time: np.ndarray, test_values: np.ndarray) -> dict[str, float] | dict[str, Any]:
    if model_time.size < 2 or model_values.size != model_time.size or test_time.size == 0 or test_values.size != test_time.size:
        return {"available": False}
    predicted = np.interp(test_time, model_time, model_values, left=model_values[0], right=model_values[-1])
    residual = predicted - test_values
    scale = max(float(np.nanmean(np.abs(test_values))), 1.0e-9)
    return {
        "available": True,
        "rmse_percent": 100.0 * float(np.sqrt(np.nanmean(np.square(residual)))) / scale,
        "mae_percent": 100.0 * float(np.nanmean(np.abs(residual))) / scale,
        "bias_percent": 100.0 * float(np.nanmean(residual)) / scale,
        "max_abs_percent": 100.0 * float(np.nanmax(np.abs(residual))) / scale,
    }


def _scalar_error(measured: float | None, predicted: float | None) -> dict[str, Any]:
    if measured is None or predicted is None:
        return {"available": False}
    scale = max(abs(float(measured)), 1.0e-9)
    return {
        "available": True,
        "measured": float(measured),
        "predicted": float(predicted),
        "delta": float(predicted) - float(measured),
        "delta_percent": 100.0 * (float(predicted) - float(measured)) / scale,
    }


def compare_model_to_test(
    dataset: TestDataset,
    summary: TestRunSummary,
    *,
    model_source: str,
    model_history: Mapping[str, Any],
    model_metrics: Mapping[str, Any],
    thermal_result: Any | None = None,
) -> ModelVsTestComparison:
    """Compare one cleaned dataset against a selected reduced-order solver history."""

    channels = dataset.cleaned_time_series_channels or dataset.time_series_channels
    test_time = np.asarray(channels.get("time_s", []), dtype=float)
    model_time = np.asarray(model_history.get("integration_time_s", []), dtype=float)
    pressure_trace_error = _trace_error(
        model_time,
        np.asarray(model_history.get("pc_pa", []), dtype=float),
        test_time,
        np.asarray(channels.get("chamber_pressure_pa", []), dtype=float),
    )
    thrust_trace_error = _trace_error(
        model_time,
        np.asarray(model_history.get("thrust_n", model_history.get("thrust_transient_actual_n", [])), dtype=float),
        test_time,
        np.asarray(channels.get("thrust_n", []), dtype=float),
    )
    regression_fit_error = None
    if summary.fuel_used_kg is not None and model_metrics.get("fuel_mass_burned_kg") is not None:
        regression_fit_error = _scalar_error(summary.fuel_used_kg, float(model_metrics.get("fuel_mass_burned_kg")))
    thermal_indicator_error = None
    if thermal_result is not None and "chamber_wall_temp_k" in channels:
        measured_temp = np.asarray(channels.get("chamber_wall_temp_k", []), dtype=float)
        predicted_temp = np.asarray(
            getattr(getattr(thermal_result.chamber_region_result, "region", None), "inner_wall_temp_history_k", []),
            dtype=float,
        )
        predicted_time = np.asarray(
            getattr(getattr(thermal_result.chamber_region_result, "region", None), "time_history_s", []),
            dtype=float,
        )
        thermal_indicator_error = _trace_error(predicted_time, predicted_temp, test_time, measured_temp)
    validity_flags = {
        "model_source_identified": bool(model_source),
        "model_history_available": bool(model_history),
        "dataset_has_time": bool(test_time.size),
    }
    comparison_metrics = {
        "pressure_rmse_percent": pressure_trace_error.get("rmse_percent"),
        "thrust_rmse_percent": thrust_trace_error.get("rmse_percent"),
        "burn_time_delta_percent": _scalar_error(summary.achieved_burn_time_s, model_metrics.get("burn_time_actual_s")).get("delta_percent"),
        "impulse_delta_percent": _scalar_error(summary.total_impulse_ns, model_metrics.get("impulse_total_ns")).get("delta_percent"),
        "avg_pressure_ratio": None
        if summary.average_chamber_pressure_pa in {None, 0.0}
        else float(model_metrics.get("pc_avg_bar", 0.0)) * 1.0e5 / float(summary.average_chamber_pressure_pa),
        "avg_thrust_ratio": None
        if summary.average_thrust_n in {None, 0.0}
        else float(model_metrics.get("thrust_avg_n", 0.0)) / float(summary.average_thrust_n),
    }
    if thermal_indicator_error is not None and test_time.size:
        comparison_metrics["thermal_peak_ratio"] = (
            None
            if not np.asarray(channels.get("chamber_wall_temp_k", []), dtype=float).size
            else float(np.nanmax(predicted_temp)) / float(np.nanmax(np.asarray(channels.get("chamber_wall_temp_k", []), dtype=float)))
            if np.nanmax(np.asarray(channels.get("chamber_wall_temp_k", []), dtype=float)) > 0.0 and predicted_temp.size
            else None
        )
    return ModelVsTestComparison(
        run_id=dataset.run_id,
        article_id=dataset.article_id,
        stage_name=dataset.stage_name,
        model_source=model_source,
        comparison_metrics=comparison_metrics,
        pressure_trace_error=pressure_trace_error,
        thrust_trace_error=thrust_trace_error,
        burn_time_error=_scalar_error(summary.achieved_burn_time_s, model_metrics.get("burn_time_actual_s")),
        impulse_error=_scalar_error(summary.total_impulse_ns, model_metrics.get("impulse_total_ns")),
        regression_fit_error=regression_fit_error,
        thermal_indicator_error=thermal_indicator_error,
        notes=["Trace comparison uses interpolation of reduced-order histories onto the cleaned test time base."],
        validity_flags=validity_flags,
    )
