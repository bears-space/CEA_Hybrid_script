"""Efficiency and nozzle-loss fitting helpers for hot-fire datasets."""

from __future__ import annotations

from typing import Sequence

from src.testing.test_types import ModelVsTestComparison


def _mean(values: Sequence[float]) -> float | None:
    numeric = [float(value) for value in values]
    return None if not numeric else sum(numeric) / len(numeric)


def fit_efficiency_corrections(
    comparisons: Sequence[ModelVsTestComparison],
    *,
    nominal_cstar_efficiency: float,
) -> tuple[float | None, float | None, list[str]]:
    """Fit c* efficiency and nozzle/thrust-loss corrections from model-vs-test ratios."""

    warnings: list[str] = []
    pressure_ratios = []
    thrust_ratios = []
    for comparison in comparisons:
        ratio = comparison.comparison_metrics.get("avg_pressure_ratio")
        thrust_ratio = comparison.comparison_metrics.get("avg_thrust_ratio")
        if ratio not in {None, 0.0}:
            pressure_ratios.append(1.0 / float(ratio))
        if thrust_ratio not in {None, 0.0}:
            thrust_ratios.append(1.0 / float(thrust_ratio))
    pressure_scale = _mean(pressure_ratios)
    thrust_scale = _mean(thrust_ratios)
    if pressure_scale is None:
        warnings.append("No usable average-pressure ratio was available for c* efficiency fitting.")
    if thrust_scale is None:
        warnings.append("No usable average-thrust ratio was available for nozzle or thrust-loss fitting.")
    fitted_cstar = None if pressure_scale is None else float(nominal_cstar_efficiency) * float(pressure_scale)
    fitted_nozzle_loss = None
    if pressure_scale is not None and thrust_scale is not None and pressure_scale > 0.0:
        fitted_nozzle_loss = float(thrust_scale) / float(pressure_scale)
    elif thrust_scale is not None:
        fitted_nozzle_loss = float(thrust_scale)
    return fitted_cstar, fitted_nozzle_loss, warnings
