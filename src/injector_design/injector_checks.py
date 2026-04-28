"""Geometry and manufacturability checks for synthesized showerhead injectors."""

from __future__ import annotations

from typing import Any, Mapping

from src.injector_design.injector_types import InjectorGeometryDefinition
from src.sizing.geometry_types import GeometryDefinition


def _check(checks: dict[str, dict[str, Any]], name: str, passed: bool, detail: str, *, severity: str = "error") -> None:
    checks[name] = {
        "passed": bool(passed),
        "detail": detail,
        "severity": severity,
    }


def evaluate_injector_checks(
    injector_geometry: InjectorGeometryDefinition,
    policy: Mapping[str, Any],
    engine_geometry: GeometryDefinition,
) -> tuple[dict[str, dict[str, Any]], bool, list[str]]:
    """Evaluate hard-fit and soft manufacturability checks for the selected injector."""

    checks: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    hole_diameter_m = float(injector_geometry.hole_diameter_m)
    plate_thickness_m = float(injector_geometry.plate_thickness_m)
    min_hole_m = float(policy["minimum_hole_diameter_mm"]) * 1.0e-3
    max_hole_m = float(policy["maximum_hole_diameter_mm"]) * 1.0e-3
    min_ligament_m = float(policy["minimum_ligament_mm"]) * 1.0e-3
    min_edge_margin_m = float(policy["minimum_edge_margin_mm"]) * 1.0e-3
    ld_min = float(policy["target_hole_ld_min"])
    ld_max = float(policy["target_hole_ld_max"])
    max_open_area_ratio = float(policy["maximum_open_area_ratio"])
    max_hole_velocity_m_s = float(policy["maximum_hole_velocity_m_s"])
    _check(checks, "positive_geometry", hole_diameter_m > 0.0 and plate_thickness_m > 0.0, "Hole diameter and plate thickness must be positive.")
    _check(checks, "hole_diameter_range", min_hole_m <= hole_diameter_m <= max_hole_m, "Hole diameter must fall inside the configured range.")
    _check(
        checks,
        "hole_count_positive",
        injector_geometry.hole_count > 0,
        "Hole count must remain positive after the fixed-hole-diameter sizing step.",
    )
    _check(checks, "active_face_fit", injector_geometry.active_face_diameter_m <= injector_geometry.plate_outer_diameter_m, "Active face must fit inside the plate outer diameter.")
    _check(checks, "ring_pattern_present", injector_geometry.hole_count > 0 and injector_geometry.ring_count >= 0, "Injector must contain a non-zero number of holes.")
    _check(checks, "minimum_ligament", injector_geometry.min_ligament_m >= min_ligament_m - 1.0e-12, "Minimum ligament requirement must be satisfied.")
    _check(checks, "minimum_edge_margin", injector_geometry.min_edge_margin_m >= min_edge_margin_m - 1.0e-12, "Minimum active-face edge margin must be satisfied.")
    _check(checks, "plate_face_size", injector_geometry.plate_outer_diameter_m <= engine_geometry.injector_face_diameter_m * 1.25, "Injector plate should remain consistent with the frozen chamber/injector face envelope.")
    _check(
        checks,
        "prechamber_consistency",
        (not injector_geometry.discharges_into_prechamber) or engine_geometry.prechamber_length_m > 0.0,
        "Discharge-to-prechamber assumption requires a non-zero prechamber length in the frozen geometry.",
    )

    ld_in_band = ld_min <= injector_geometry.hole_ld_ratio <= ld_max
    _check(checks, "hole_ld_target", ld_in_band, "Hole L/D target band is advisory.", severity="warning")
    if not ld_in_band:
        warnings.append(
            f"Hole L/D={injector_geometry.hole_ld_ratio:.2f} sits outside the target band [{ld_min:.2f}, {ld_max:.2f}]."
        )

    open_area_ok = injector_geometry.geometric_open_area_ratio <= max_open_area_ratio
    _check(checks, "open_area_ratio", open_area_ok, "Open-area ratio target is advisory.", severity="warning")
    if not open_area_ok:
        warnings.append(
            f"Open-area ratio {injector_geometry.geometric_open_area_ratio:.3f} exceeds the configured warning threshold {max_open_area_ratio:.3f}."
        )

    velocity_ok = injector_geometry.design_hole_velocity_m_s <= max_hole_velocity_m_s
    _check(checks, "hole_velocity", velocity_ok, "Per-hole liquid velocity target is advisory.", severity="warning")
    if not velocity_ok:
        warnings.append(
            f"Estimated per-hole velocity {injector_geometry.design_hole_velocity_m_s:.2f} m/s exceeds the configured advisory limit {max_hole_velocity_m_s:.2f} m/s."
        )

    valid = all(entry["passed"] or entry["severity"] == "warning" for entry in checks.values())
    return checks, valid, warnings
