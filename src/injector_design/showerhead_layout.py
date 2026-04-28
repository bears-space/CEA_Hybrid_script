"""Ring-pattern generation for practical axial showerhead injectors."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

import numpy as np

from src.injector_design.injector_types import InjectorRingDefinition


@dataclass(frozen=True)
class ShowerheadLayoutResult:
    ring_definitions: list[InjectorRingDefinition]
    center_hole_enabled: bool
    min_ligament_m: float
    min_edge_margin_m: float
    failure_reason: str | None = None


def _candidate_radii(
    *,
    outer_hole_center_radius_m: float,
    ring_count: int,
    minimum_pitch_m: float,
    center_hole_enabled: bool,
    spacing_mode: str,
) -> np.ndarray | None:
    if ring_count == 0:
        return np.array([], dtype=float)

    inner_min_m = minimum_pitch_m if center_hole_enabled else minimum_pitch_m
    if spacing_mode == "minimum_pitch":
        inner_radius_m = outer_hole_center_radius_m - (ring_count - 1) * minimum_pitch_m
        if inner_radius_m < inner_min_m - 1.0e-12:
            return None
        return np.array(
            [inner_radius_m + index * minimum_pitch_m for index in range(ring_count)],
            dtype=float,
        )

    if ring_count == 1:
        if outer_hole_center_radius_m < inner_min_m - 1.0e-12:
            return None
        return np.array([outer_hole_center_radius_m], dtype=float)

    span_m = outer_hole_center_radius_m - inner_min_m
    if span_m < (ring_count - 1) * minimum_pitch_m - 1.0e-12:
        return None
    return np.linspace(inner_min_m, outer_hole_center_radius_m, ring_count, dtype=float)


def _ring_capacities(radii_m: Sequence[float], minimum_pitch_m: float) -> list[int]:
    capacities: list[int] = []
    for radius_m in radii_m:
        capacity = int(math.floor((2.0 * math.pi * float(radius_m)) / minimum_pitch_m))
        capacities.append(max(capacity, 1))
    return capacities


def _distribute_ring_holes(capacities: Sequence[int], remaining_holes: int) -> list[int] | None:
    ring_count = len(capacities)
    if ring_count == 0:
        return [] if remaining_holes == 0 else None
    if remaining_holes < ring_count or remaining_holes > sum(capacities):
        return None

    holes = [1] * ring_count
    extra_capacity = [capacity - 1 for capacity in capacities]
    extra_holes = remaining_holes - ring_count
    if extra_holes <= 0:
        return holes

    total_extra_capacity = sum(extra_capacity)
    if total_extra_capacity <= 0:
        return None if extra_holes > 0 else holes

    remainders: list[tuple[float, int]] = []
    for index, capacity in enumerate(extra_capacity):
        share = extra_holes * capacity / total_extra_capacity if total_extra_capacity > 0 else 0.0
        assigned = min(int(math.floor(share)), capacity)
        holes[index] += assigned
        remainders.append((share - assigned, index))

    remaining = remaining_holes - sum(holes)
    for _, index in sorted(remainders, reverse=True):
        if remaining <= 0:
            break
        if holes[index] < capacities[index]:
            holes[index] += 1
            remaining -= 1

    if remaining > 0:
        for index in sorted(range(ring_count), key=lambda item: capacities[item], reverse=True):
            while remaining > 0 and holes[index] < capacities[index]:
                holes[index] += 1
                remaining -= 1
            if remaining <= 0:
                break

    return None if remaining > 0 else holes


def generate_showerhead_layout(
    *,
    hole_count: int,
    hole_diameter_m: float,
    active_face_diameter_m: float,
    minimum_ligament_m: float,
    minimum_edge_margin_m: float,
    allow_center_hole: bool,
    max_ring_count: int,
    spacing_mode: str,
) -> ShowerheadLayoutResult:
    """Place holes on concentric rings and enforce simple pitch-based fit checks."""

    hole_radius_m = 0.5 * float(hole_diameter_m)
    active_face_radius_m = 0.5 * float(active_face_diameter_m)
    outer_hole_center_radius_m = active_face_radius_m - float(minimum_edge_margin_m) - hole_radius_m
    minimum_pitch_m = float(hole_diameter_m) + float(minimum_ligament_m)
    if hole_count <= 0:
        return ShowerheadLayoutResult([], False, 0.0, 0.0, "hole_count must be positive")
    if hole_diameter_m <= 0.0:
        return ShowerheadLayoutResult([], False, 0.0, 0.0, "hole diameter must be positive")
    if outer_hole_center_radius_m <= 0.0:
        return ShowerheadLayoutResult([], False, 0.0, 0.0, "active face is too small for the requested hole size")

    best_result: ShowerheadLayoutResult | None = None
    center_options = [False, True] if allow_center_hole and hole_count >= 1 else [False]
    for center_hole_enabled in center_options:
        center_hole_count = 1 if center_hole_enabled else 0
        remaining_holes = hole_count - center_hole_count
        minimum_ring_count = 0 if remaining_holes == 0 else 1
        for ring_count in range(minimum_ring_count, int(max_ring_count) + 1):
            radii_m = _candidate_radii(
                outer_hole_center_radius_m=outer_hole_center_radius_m,
                ring_count=ring_count,
                minimum_pitch_m=minimum_pitch_m,
                center_hole_enabled=center_hole_enabled,
                spacing_mode=spacing_mode,
            )
            if radii_m is None:
                continue

            capacities = _ring_capacities(radii_m, minimum_pitch_m)
            holes_in_rings = _distribute_ring_holes(capacities, remaining_holes)
            if holes_in_rings is None:
                continue

            ring_definitions: list[InjectorRingDefinition] = []
            circumferential_spacing_values: list[float] = []
            for ring_index, (radius_m, holes_in_ring) in enumerate(zip(radii_m, holes_in_rings), start=1):
                circumference_m = 2.0 * math.pi * float(radius_m)
                spacing_m = float("inf") if holes_in_ring <= 1 else (circumference_m / holes_in_ring) - hole_diameter_m
                circumferential_spacing_values.append(spacing_m)
                angular_offset_deg = 0.0 if ring_index % 2 else (180.0 / holes_in_ring)
                ring_definitions.append(
                    InjectorRingDefinition(
                        ring_index=ring_index,
                        ring_radius_m=float(radius_m),
                        holes_in_ring=int(holes_in_ring),
                        angular_offset_deg=float(angular_offset_deg),
                        circumferential_spacing_m=spacing_m,
                    )
                )

            radial_spacing_values = [
                (float(radii_m[index + 1]) - float(radii_m[index])) - hole_diameter_m
                for index in range(max(len(radii_m) - 1, 0))
            ]
            if center_hole_enabled and len(radii_m):
                radial_spacing_values.append(float(radii_m[0]) - hole_diameter_m)
            active_min_ligament_m = min(
                [value for value in circumferential_spacing_values if math.isfinite(value)] + radial_spacing_values + [float("inf")]
            )
            active_edge_margin_m = active_face_radius_m - (max(radii_m, default=0.0) + hole_radius_m)
            if active_min_ligament_m < minimum_ligament_m - 1.0e-12:
                continue
            if active_edge_margin_m < minimum_edge_margin_m - 1.0e-12:
                continue

            candidate = ShowerheadLayoutResult(
                ring_definitions=ring_definitions,
                center_hole_enabled=center_hole_enabled,
                min_ligament_m=float(active_min_ligament_m),
                min_edge_margin_m=float(active_edge_margin_m),
            )
            if best_result is None:
                best_result = candidate
                continue
            if len(candidate.ring_definitions) < len(best_result.ring_definitions):
                best_result = candidate
                continue
            if candidate.min_ligament_m > best_result.min_ligament_m:
                best_result = candidate

    if best_result is not None:
        return best_result
    return ShowerheadLayoutResult([], False, 0.0, 0.0, "no valid ring pattern fits inside the active face")
