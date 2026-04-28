"""Shared helpers for a conical converging-throat-diverging contour with a finite throat blend."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ConicalNozzleContour:
    """First-pass conical contour metadata shared by geometry and downstream tools."""

    contour_style: str
    chamber_radius_m: float
    throat_radius_m: float
    exit_radius_m: float
    converging_half_angle_deg: float
    diverging_half_angle_deg: float
    throat_blend_radius_m: float
    converging_straight_length_m: float
    diverging_straight_length_m: float
    converging_blend_arc_length_m: float
    diverging_blend_arc_length_m: float
    converging_section_length_m: float
    converging_section_arc_length_m: float
    nozzle_length_m: float
    nozzle_arc_length_m: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _slope_from_half_angle_deg(half_angle_deg: float) -> float:
    bounded = max(abs(float(half_angle_deg)), 1.0e-3)
    return math.tan(math.radians(bounded))


def _positive_angle_rad(half_angle_deg: float) -> float:
    return math.radians(max(abs(float(half_angle_deg)), 1.0e-3))


def _blend_offsets(blend_radius_m: float, half_angle_deg: float) -> tuple[float, float, float]:
    """Return axial offset, radial offset, and arc length for a throat-side blend."""

    if blend_radius_m <= 0.0:
        return 0.0, 0.0, 0.0
    half_angle_rad = _positive_angle_rad(half_angle_deg)
    axial_offset_m = float(blend_radius_m) * math.sin(half_angle_rad)
    radial_offset_m = float(blend_radius_m) * (1.0 - math.cos(half_angle_rad))
    arc_length_m = float(blend_radius_m) * half_angle_rad
    return axial_offset_m, radial_offset_m, arc_length_m


def _max_blend_radius_for_delta(delta_radius_m: float, half_angle_deg: float) -> float:
    if delta_radius_m <= 0.0:
        return 0.0
    half_angle_rad = _positive_angle_rad(half_angle_deg)
    radial_factor = 1.0 - math.cos(half_angle_rad)
    if radial_factor <= 1.0e-12:
        return 0.0
    return float(delta_radius_m) / radial_factor


def _straight_section_length(radius_start_m: float, radius_end_m: float, half_angle_deg: float) -> float:
    if radius_start_m <= radius_end_m:
        return 0.0
    return float(radius_start_m - radius_end_m) / _slope_from_half_angle_deg(half_angle_deg)


def build_conical_nozzle_contour(
    *,
    chamber_diameter_m: float,
    throat_diameter_m: float,
    exit_diameter_m: float,
    converging_half_angle_deg: float,
    diverging_half_angle_deg: float,
    throat_blend_radius_factor: float,
) -> ConicalNozzleContour:
    """Return the first-pass converging and diverging lengths for a blended conical contour."""

    chamber_radius_m = max(float(chamber_diameter_m) * 0.5, 0.0)
    throat_radius_m = max(float(throat_diameter_m) * 0.5, 0.0)
    exit_radius_m = max(float(exit_diameter_m) * 0.5, throat_radius_m)
    requested_throat_blend_radius_m = max(float(throat_blend_radius_factor), 0.0) * throat_radius_m
    max_converging_blend_radius_m = _max_blend_radius_for_delta(chamber_radius_m - throat_radius_m, converging_half_angle_deg)
    max_diverging_blend_radius_m = _max_blend_radius_for_delta(exit_radius_m - throat_radius_m, diverging_half_angle_deg)
    throat_blend_radius_m = min(
        requested_throat_blend_radius_m,
        max_converging_blend_radius_m,
        max_diverging_blend_radius_m,
    )

    converging_axial_offset_m, converging_radial_offset_m, converging_blend_arc_length_m = _blend_offsets(
        throat_blend_radius_m,
        converging_half_angle_deg,
    )
    diverging_axial_offset_m, diverging_radial_offset_m, diverging_blend_arc_length_m = _blend_offsets(
        throat_blend_radius_m,
        diverging_half_angle_deg,
    )

    converging_tangent_radius_m = throat_radius_m + converging_radial_offset_m
    diverging_tangent_radius_m = throat_radius_m + diverging_radial_offset_m

    converging_straight_length_m = _straight_section_length(
        chamber_radius_m,
        converging_tangent_radius_m,
        converging_half_angle_deg,
    )
    diverging_straight_length_m = _straight_section_length(
        exit_radius_m,
        diverging_tangent_radius_m,
        diverging_half_angle_deg,
    )

    converging_length_m = converging_straight_length_m + converging_axial_offset_m
    nozzle_length_m = diverging_straight_length_m + diverging_axial_offset_m

    return ConicalNozzleContour(
        contour_style="conical_blended",
        chamber_radius_m=chamber_radius_m,
        throat_radius_m=throat_radius_m,
        exit_radius_m=exit_radius_m,
        converging_half_angle_deg=float(converging_half_angle_deg),
        diverging_half_angle_deg=float(diverging_half_angle_deg),
        throat_blend_radius_m=throat_blend_radius_m,
        converging_straight_length_m=converging_straight_length_m,
        diverging_straight_length_m=diverging_straight_length_m,
        converging_blend_arc_length_m=converging_blend_arc_length_m,
        diverging_blend_arc_length_m=diverging_blend_arc_length_m,
        converging_section_length_m=converging_length_m,
        converging_section_arc_length_m=converging_straight_length_m + converging_blend_arc_length_m,
        nozzle_length_m=nozzle_length_m,
        nozzle_arc_length_m=diverging_straight_length_m + diverging_blend_arc_length_m,
    )
