"""Thermal correlation helpers for test-measured temperature indicators."""

from __future__ import annotations

from typing import Sequence

from src.testing.test_types import ModelVsTestComparison


def fit_thermal_multiplier(comparisons: Sequence[ModelVsTestComparison]) -> tuple[float | None, list[str]]:
    """Estimate a first-pass thermal multiplier from measured wall-temperature indicators."""

    ratios = []
    for comparison in comparisons:
        ratio = comparison.comparison_metrics.get("thermal_peak_ratio")
        if ratio not in {None, 0.0}:
            ratios.append(1.0 / float(ratio))
    if not ratios:
        return None, ["No usable thermal-indicator channels were available for thermal multiplier fitting."]
    return float(sum(ratios) / len(ratios)), []
