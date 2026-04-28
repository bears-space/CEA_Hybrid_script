"""Fuel-grain support and retention placeholder checks."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from src.sizing.geometry_types import GeometryDefinition
from src.structural.structural_types import GrainSupportSizingResult


def _final_web_thickness_m(
    geometry: GeometryDefinition,
    nominal_payload: Mapping[str, Any],
    ballistics_payload: Mapping[str, Any] | None,
) -> float | None:
    if ballistics_payload is not None:
        history = ballistics_payload["result"].get("history", {})
        values = np.asarray(history.get("grain_web_remaining_mm", []), dtype=float)
        if values.size:
            return float(values[-1]) * 1.0e-3
    history = nominal_payload["result"].get("history", {})
    values = np.asarray(history.get("grain_web_remaining_m", []), dtype=float)
    if values.size:
        return float(values[-1])
    return None


def evaluate_grain_support(
    structural_config: Mapping[str, Any],
    geometry: GeometryDefinition,
    nominal_payload: Mapping[str, Any],
    ballistics_payload: Mapping[str, Any] | None = None,
) -> GrainSupportSizingResult:
    """Return geometry-driven support and retention warnings for the fuel grain."""

    settings = dict(structural_config.get("grain_support", {}))
    warnings: list[str] = []
    actual_clearance_m = 0.5 * float(geometry.chamber_id_m) - float(geometry.grain_outer_radius_m)
    initial_web_thickness_m = float(geometry.radial_web_initial_m)
    final_web_thickness_m = _final_web_thickness_m(geometry, nominal_payload, ballistics_payload)
    grain_slenderness_ratio = float(geometry.grain_length_m) / max(2.0 * float(geometry.grain_outer_radius_m), 1.0e-12)
    web_slenderness_ratio = float(geometry.grain_length_m) / max(2.0 * initial_web_thickness_m, 1.0e-12)

    if actual_clearance_m < float(settings["minimum_clearance_m"]):
        warnings.append("Radial grain-to-chamber clearance is below the configured structural minimum.")
    if final_web_thickness_m is not None and final_web_thickness_m < float(settings["minimum_final_web_m"]):
        warnings.append("Predicted final grain web thickness is below the configured structural minimum.")
    if grain_slenderness_ratio > float(settings["max_grain_slenderness_ratio"]):
        warnings.append("Grain slenderness exceeds the configured support warning limit.")
    if web_slenderness_ratio > float(settings["max_web_slenderness_ratio"]):
        warnings.append("Initial grain web slenderness exceeds the configured warning limit.")

    return GrainSupportSizingResult(
        retention_concept=str(settings["retention_concept"]),
        initial_web_thickness_m=initial_web_thickness_m,
        final_web_thickness_m=final_web_thickness_m,
        chamber_radial_clearance_m=float(actual_clearance_m),
        grain_length_m=float(geometry.grain_length_m),
        grain_outer_radius_m=float(geometry.grain_outer_radius_m),
        grain_slenderness_ratio=float(grain_slenderness_ratio),
        web_slenderness_ratio=float(web_slenderness_ratio),
        valid=not warnings,
        warnings=warnings,
        notes=["Fuel-grain retention is currently a geometry-and-clearance placeholder, not a full mechanics model."],
    )
