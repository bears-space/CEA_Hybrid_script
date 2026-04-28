"""Expansion-state classification helpers for nozzle off-design checks."""

from __future__ import annotations

from typing import Mapping


def exit_to_ambient_ratio(exit_pressure_pa: float, ambient_pressure_pa: float) -> float | None:
    """Return the exit-to-ambient pressure ratio when it is defined."""

    if ambient_pressure_pa <= 0.0:
        return None
    return float(exit_pressure_pa) / float(ambient_pressure_pa)


def classify_expansion_state(
    *,
    exit_pressure_pa: float,
    ambient_pressure_pa: float,
    thresholds: Mapping[str, float],
) -> str:
    """Classify nozzle expansion state using explicit pressure-ratio thresholds."""

    if ambient_pressure_pa <= 0.0:
        return "strongly_underexpanded"
    ratio = exit_to_ambient_ratio(exit_pressure_pa, ambient_pressure_pa)
    assert ratio is not None
    if ratio < float(thresholds["strongly_overexpanded_ratio"]):
        return "strongly_overexpanded"
    if ratio < float(thresholds["moderately_overexpanded_ratio"]):
        return "moderately_overexpanded"
    if ratio <= float(thresholds["near_matched_upper_ratio"]):
        return "near_matched"
    if ratio <= float(thresholds["moderately_underexpanded_ratio"]):
        return "moderately_underexpanded"
    return "strongly_underexpanded"
