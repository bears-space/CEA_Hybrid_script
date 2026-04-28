"""Reduced-order separation-risk and side-load placeholder checks."""

from __future__ import annotations

from typing import Mapping, Sequence

from src.nozzle_offdesign.expansion_state import exit_to_ambient_ratio
from src.nozzle_offdesign.nozzle_offdesign_types import NozzleOperatingPoint, SeparationRiskResult


def separation_cf_penalty_multiplier(
    operating_point: NozzleOperatingPoint,
    thresholds: Mapping[str, float],
    penalties: Mapping[str, float],
) -> float:
    """Return an optional conservative Cf penalty multiplier for separated-flow risk."""

    ratio = exit_to_ambient_ratio(operating_point.exit_pressure_pa, operating_point.ambient_pressure_pa)
    if ratio is None:
        return 1.0
    if ratio < float(thresholds["high_risk_ratio"]):
        return float(penalties.get("high_risk_cf_multiplier", 0.9))
    if ratio < float(thresholds["moderate_risk_ratio"]):
        return float(penalties.get("moderate_risk_cf_multiplier", 0.97))
    return 1.0


def evaluate_separation_risk(
    operating_points: Sequence[NozzleOperatingPoint],
    thresholds: Mapping[str, float],
) -> SeparationRiskResult:
    """Evaluate a reduced-order separation-risk summary across operating points."""

    if not operating_points:
        return SeparationRiskResult(
            risk_level="unknown",
            margin_metric=0.0,
            likely_overexpanded=False,
            likely_underexpanded=False,
            startup_risk_flag=False,
            shutdown_risk_flag=False,
            separation_warning="No operating points were available for the separation heuristic.",
            model_assumptions=["Pressure-ratio separation heuristic only."],
        )

    ratios = [
        exit_to_ambient_ratio(point.exit_pressure_pa, point.ambient_pressure_pa)
        for point in operating_points
        if point.ambient_pressure_pa > 0.0
    ]
    valid_ratios = [ratio for ratio in ratios if ratio is not None]
    min_ratio = min(valid_ratios) if valid_ratios else float("inf")
    max_ratio = max(valid_ratios) if valid_ratios else float("inf")
    likely_overexpanded = min_ratio < float(thresholds["moderate_risk_ratio"])
    likely_underexpanded = max_ratio > float(thresholds["underexpanded_notice_ratio"])
    if min_ratio < float(thresholds["high_risk_ratio"]):
        risk_level = "high"
    elif min_ratio < float(thresholds["moderate_risk_ratio"]):
        risk_level = "moderate"
    else:
        risk_level = "low"

    startup_window_fraction = float(thresholds["startup_window_fraction"])
    shutdown_window_fraction = float(thresholds["shutdown_window_fraction"])
    times = [point.time_s for point in operating_points if point.time_s is not None]
    burn_duration_s = max(times) if times else 0.0
    startup_risk_flag = any(
        point.time_s is not None
        and burn_duration_s > 0.0
        and point.time_s <= startup_window_fraction * burn_duration_s
        and exit_to_ambient_ratio(point.exit_pressure_pa, point.ambient_pressure_pa) is not None
        and exit_to_ambient_ratio(point.exit_pressure_pa, point.ambient_pressure_pa) < float(thresholds["moderate_risk_ratio"])
        for point in operating_points
    )
    shutdown_risk_flag = any(
        point.time_s is not None
        and burn_duration_s > 0.0
        and point.time_s >= (1.0 - shutdown_window_fraction) * burn_duration_s
        and exit_to_ambient_ratio(point.exit_pressure_pa, point.ambient_pressure_pa) is not None
        and exit_to_ambient_ratio(point.exit_pressure_pa, point.ambient_pressure_pa) < float(thresholds["moderate_risk_ratio"])
        for point in operating_points
    )
    warning = None
    if risk_level == "high":
        warning = "Exit pressure falls well below ambient for at least part of the case; separated flow is plausible."
    elif risk_level == "moderate":
        warning = "Exit pressure approaches or drops below ambient for part of the case; monitor for separation sensitivity."
    return SeparationRiskResult(
        risk_level=risk_level,
        margin_metric=min_ratio if valid_ratios else 0.0,
        likely_overexpanded=likely_overexpanded,
        likely_underexpanded=likely_underexpanded,
        startup_risk_flag=startup_risk_flag,
        shutdown_risk_flag=shutdown_risk_flag,
        separation_warning=warning,
        model_assumptions=[
            "Pressure-ratio separation heuristic only.",
            "No detailed separated-flow internal-nozzle model or side-load prediction is included.",
        ],
    )
