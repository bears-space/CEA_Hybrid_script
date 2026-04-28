"""Regression-law calibration helpers for hot-fire datasets."""

from __future__ import annotations

from typing import Mapping, Sequence

from src.testing.test_types import ModelVsTestComparison, TestRunSummary


def fit_regression_parameters(
    run_summaries: Sequence[TestRunSummary],
    comparisons: Sequence[ModelVsTestComparison],
    *,
    nominal_a_reg_si: float,
    nominal_n_reg: float,
) -> tuple[dict[str, float], list[str]]:
    """Fit first-pass regression parameter updates from available hot-fire summaries."""

    del run_summaries
    warnings: list[str] = []
    usable_ratios = []
    for comparison in comparisons:
        if comparison.regression_fit_error and comparison.regression_fit_error.get("available"):
            measured = float(comparison.regression_fit_error["measured"])
            predicted = float(comparison.regression_fit_error["predicted"])
            if predicted > 0.0:
                usable_ratios.append(measured / predicted)
    if not usable_ratios:
        warnings.append("Regression parameter fit fell back to the nominal regression law because no measured fuel-burn indicator was available.")
        return {
            "a_reg_si": float(nominal_a_reg_si),
            "n_reg": float(nominal_n_reg),
            "a_multiplier": 1.0,
        }, warnings
    a_multiplier = sum(usable_ratios) / len(usable_ratios)
    return {
        "a_reg_si": float(nominal_a_reg_si) * float(a_multiplier),
        "n_reg": float(nominal_n_reg),
        "a_multiplier": float(a_multiplier),
    }, warnings
