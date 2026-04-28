"""Residual construction and summary metrics for cold-flow model validation."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from src.hydraulic_validation.coldflow_types import ColdFlowDataset, ColdFlowPoint, HydraulicPrediction, HydraulicResidual


def measured_feed_delta_p_pa(point: ColdFlowPoint) -> float | None:
    if point.measured_delta_p_feed_pa is not None:
        return float(point.measured_delta_p_feed_pa)
    if point.upstream_pressure_pa is not None and point.injector_inlet_pressure_pa is not None:
        return float(point.upstream_pressure_pa) - float(point.injector_inlet_pressure_pa)
    return None


def measured_injector_delta_p_pa(point: ColdFlowPoint) -> float | None:
    if point.measured_delta_p_injector_pa is not None:
        return float(point.measured_delta_p_injector_pa)
    if point.injector_inlet_pressure_pa is not None and point.downstream_pressure_pa is not None:
        return float(point.injector_inlet_pressure_pa) - float(point.downstream_pressure_pa)
    return None


def _error_percent(error_value: float | None, measured_value: float | None) -> float | None:
    if error_value is None or measured_value is None or abs(float(measured_value)) <= 1.0e-12:
        return None
    return 100.0 * float(error_value) / float(measured_value)


def build_residual(point: ColdFlowPoint, prediction: HydraulicPrediction) -> HydraulicResidual:
    """Build one residual record from a measured point and a model prediction."""

    measured_feed_pa = measured_feed_delta_p_pa(point)
    measured_inj_pa = measured_injector_delta_p_pa(point)
    measured_inlet_pa = float(point.injector_inlet_pressure_pa) if point.injector_inlet_pressure_pa is not None else None
    measured_mdot_kg_s = float(point.measured_mdot_kg_s) if point.measured_mdot_kg_s is not None else None

    mdot_error_kg_s = (
        float(prediction.predicted_mdot_kg_s) - measured_mdot_kg_s
        if measured_mdot_kg_s is not None
        else None
    )
    feed_error_pa = (
        float(prediction.predicted_feed_delta_p_pa) - measured_feed_pa
        if measured_feed_pa is not None
        else None
    )
    injector_error_pa = (
        float(prediction.predicted_injector_delta_p_pa) - measured_inj_pa
        if measured_inj_pa is not None
        else None
    )
    inlet_error_pa = (
        float(prediction.predicted_injector_inlet_pressure_pa) - measured_inlet_pa
        if measured_inlet_pa is not None
        else None
    )

    return HydraulicResidual(
        test_id=point.test_id,
        point_index=point.point_index,
        model_source=prediction.model_source,
        measured_mdot_kg_s=measured_mdot_kg_s,
        predicted_mdot_kg_s=float(prediction.predicted_mdot_kg_s),
        mdot_error_kg_s=mdot_error_kg_s,
        mdot_error_percent=_error_percent(mdot_error_kg_s, measured_mdot_kg_s),
        measured_feed_delta_p_pa=measured_feed_pa,
        predicted_feed_delta_p_pa=float(prediction.predicted_feed_delta_p_pa),
        feed_delta_p_error_pa=feed_error_pa,
        feed_delta_p_error_percent=_error_percent(feed_error_pa, measured_feed_pa),
        measured_injector_delta_p_pa=measured_inj_pa,
        predicted_injector_delta_p_pa=float(prediction.predicted_injector_delta_p_pa),
        injector_delta_p_error_pa=injector_error_pa,
        injector_delta_p_error_percent=_error_percent(injector_error_pa, measured_inj_pa),
        measured_injector_inlet_pressure_pa=measured_inlet_pa,
        predicted_injector_inlet_pressure_pa=float(prediction.predicted_injector_inlet_pressure_pa),
        injector_inlet_pressure_error_pa=inlet_error_pa,
        injector_inlet_pressure_error_percent=_error_percent(inlet_error_pa, measured_inlet_pa),
    )


def build_residuals(dataset: ColdFlowDataset, predictions: list[HydraulicPrediction]) -> list[HydraulicResidual]:
    """Build residual records for a full dataset."""

    prediction_by_key = {(prediction.test_id, prediction.point_index): prediction for prediction in predictions}
    residuals: list[HydraulicResidual] = []
    for point in dataset.points:
        key = (point.test_id, point.point_index)
        residuals.append(build_residual(point, prediction_by_key[key]))
    return residuals


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "rmse": None, "mae": None, "bias": None, "max_abs": None}
    array = np.asarray(values, dtype=float)
    return {
        "count": int(array.size),
        "rmse": float(np.sqrt(np.mean(array**2))),
        "mae": float(np.mean(np.abs(array))),
        "bias": float(np.mean(array)),
        "max_abs": float(np.max(np.abs(array))),
    }


def residual_statistics(dataset: ColdFlowDataset, residuals: list[HydraulicResidual]) -> dict[str, Any]:
    """Summarize residual performance and data coverage."""

    stats = {
        "mdot_error_kg_s": _summary(
            [float(item.mdot_error_kg_s) for item in residuals if item.mdot_error_kg_s is not None]
        ),
        "mdot_error_percent": _summary(
            [float(item.mdot_error_percent) for item in residuals if item.mdot_error_percent is not None]
        ),
        "feed_delta_p_error_pa": _summary(
            [float(item.feed_delta_p_error_pa) for item in residuals if item.feed_delta_p_error_pa is not None]
        ),
        "injector_delta_p_error_pa": _summary(
            [float(item.injector_delta_p_error_pa) for item in residuals if item.injector_delta_p_error_pa is not None]
        ),
        "injector_inlet_pressure_error_pa": _summary(
            [
                float(item.injector_inlet_pressure_error_pa)
                for item in residuals
                if item.injector_inlet_pressure_error_pa is not None
            ]
        ),
        "coverage": {
            "point_count": len(dataset.points),
            "measured_mdot_range_kg_s": [
                float(min(point.measured_mdot_kg_s for point in dataset.points if point.measured_mdot_kg_s is not None)),
                float(max(point.measured_mdot_kg_s for point in dataset.points if point.measured_mdot_kg_s is not None)),
            ],
            "upstream_pressure_range_pa": [
                float(min(point.upstream_pressure_pa for point in dataset.points if point.upstream_pressure_pa is not None))
                if any(point.upstream_pressure_pa is not None for point in dataset.points)
                else None,
                float(max(point.upstream_pressure_pa for point in dataset.points if point.upstream_pressure_pa is not None))
                if any(point.upstream_pressure_pa is not None for point in dataset.points)
                else None,
            ],
            "downstream_pressure_range_pa": [
                float(min(point.downstream_pressure_pa for point in dataset.points if point.downstream_pressure_pa is not None)),
                float(max(point.downstream_pressure_pa for point in dataset.points if point.downstream_pressure_pa is not None)),
            ],
        },
    }
    return stats


def residual_rows(residuals: list[HydraulicResidual], *, comparison_label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for residual in residuals:
        row = residual.to_dict()
        row["comparison_label"] = comparison_label
        rows.append(row)
    return rows


def prediction_rows(predictions: list[HydraulicPrediction], *, comparison_label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for prediction in predictions:
        row = prediction.to_dict()
        row["comparison_label"] = comparison_label
        rows.append(row)
    return rows
