"""Placeholder plenum and head-end geometry assumptions for injector design."""

from __future__ import annotations

from src.sizing.geometry_rules import area_from_diameter
from src.sizing.geometry_types import GeometryDefinition


def initialize_plenum_placeholder(
    policy: dict,
    engine_geometry: GeometryDefinition,
    *,
    active_face_diameter_m: float,
) -> dict[str, float | bool]:
    """Return simple plenum and face-setback placeholders for later refinement."""

    plenum_depth_m = float(policy["plenum_depth_guess_mm"]) * 1.0e-3
    plenum_diameter_m = min(float(engine_geometry.injector_face_diameter_m), float(active_face_diameter_m))
    plenum_volume_m3 = area_from_diameter(plenum_diameter_m) * plenum_depth_m
    if bool(engine_geometry.injector_discharges_to_prechamber):
        face_to_grain_distance_m = float(engine_geometry.prechamber_length_m)
    else:
        face_to_grain_distance_m = float(policy["face_to_grain_distance_guess_mm"]) * 1.0e-3
    return {
        "plenum_depth_m": plenum_depth_m,
        "plenum_diameter_m": plenum_diameter_m,
        "plenum_volume_m3": plenum_volume_m3,
        "face_to_grain_distance_m": face_to_grain_distance_m,
        "discharges_into_prechamber": bool(engine_geometry.injector_discharges_to_prechamber),
    }
