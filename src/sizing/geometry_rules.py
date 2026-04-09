"""Deterministic geometry sizing helpers and sanity checks for Step 2."""

from __future__ import annotations

import math
from typing import Any, Mapping

from src.sizing.geometry_types import GeometryDefinition


def area_from_diameter(diameter_m: float) -> float:
    radius_m = 0.5 * float(diameter_m)
    return math.pi * radius_m * radius_m


def diameter_from_area(area_m2: float) -> float:
    if area_m2 <= 0.0:
        raise ValueError("Area must be positive to compute a diameter.")
    return math.sqrt((4.0 * float(area_m2)) / math.pi)


def cylinder_volume_from_diameter(length_m: float, diameter_m: float) -> float:
    return area_from_diameter(diameter_m) * float(length_m)


def cylindrical_port_volume(length_m: float, radius_m: float, port_count: int) -> float:
    return math.pi * float(radius_m) ** 2 * float(length_m) * int(port_count)


def _check(
    passed: bool,
    value: Any,
    limit: Any,
    note: str,
    *,
    hard: bool = True,
) -> dict[str, Any]:
    return {
        "passed": bool(passed),
        "hard": bool(hard),
        "value": value,
        "limit": limit,
        "note": note,
    }


def evaluate_geometry_checks(
    geometry: GeometryDefinition,
    geometry_policy: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], bool, list[str]]:
    checks: dict[str, dict[str, Any]] = {}

    chamber_to_throat = geometry.chamber_id_m / geometry.throat_diameter_m if geometry.throat_diameter_m > 0.0 else math.inf
    port_to_throat = (2.0 * geometry.port_radius_initial_m) / geometry.throat_diameter_m if geometry.throat_diameter_m > 0.0 else math.inf
    free_volume_envelope_m3 = geometry.chamber_cross_section_area_m2 * (
        geometry.prechamber_length_m + geometry.grain_length_m + geometry.postchamber_length_m
    )

    checks["positive_major_dimensions"] = _check(
        all(
            value > 0.0
            for value in (
                geometry.chamber_id_m,
                geometry.injector_face_diameter_m,
                geometry.grain_length_m,
                geometry.port_radius_initial_m,
                geometry.grain_outer_radius_m,
                geometry.throat_diameter_m,
                geometry.nozzle_exit_diameter_m,
                geometry.injector_plate_thickness_m,
                geometry.chamber_wall_thickness_guess_m,
            )
        ),
        {
            "chamber_id_m": geometry.chamber_id_m,
            "injector_face_diameter_m": geometry.injector_face_diameter_m,
            "grain_length_m": geometry.grain_length_m,
            "port_radius_initial_m": geometry.port_radius_initial_m,
            "grain_outer_radius_m": geometry.grain_outer_radius_m,
            "throat_diameter_m": geometry.throat_diameter_m,
            "nozzle_exit_diameter_m": geometry.nozzle_exit_diameter_m,
        },
        "> 0",
        "All frozen diameters, radii, and lengths must remain positive.",
    )
    checks["positive_prechambers_and_postchambers"] = _check(
        (not geometry.prechamber_enabled or geometry.prechamber_length_m > 0.0)
        and (not geometry.postchamber_enabled or geometry.postchamber_length_m > 0.0),
        {
            "prechamber_length_m": geometry.prechamber_length_m,
            "postchamber_length_m": geometry.postchamber_length_m,
        },
        "> 0 when enabled",
        "Enabled prechamber and postchamber sections must have positive length.",
    )
    checks["grain_outer_radius_gt_port_radius"] = _check(
        geometry.grain_outer_radius_m > geometry.port_radius_initial_m,
        geometry.grain_outer_radius_m - geometry.port_radius_initial_m,
        "> 0 m",
        "Grain outer radius must exceed the initial port radius.",
    )
    checks["radial_web_margin"] = _check(
        geometry.radial_web_initial_m >= float(geometry_policy["min_radial_web_m"]),
        geometry.radial_web_initial_m,
        {"min_m": float(geometry_policy["min_radial_web_m"])},
        "Initial radial web should stay above the configured minimum margin.",
    )
    checks["total_length_exceeds_grain_length"] = _check(
        geometry.total_chamber_length_m > geometry.grain_length_m,
        geometry.total_chamber_length_m,
        f"> {geometry.grain_length_m}",
        "Total chamber stack-up must exceed the grain segment length.",
    )
    checks["injector_face_margin_factor"] = _check(
        geometry.injector_face_diameter_m >= geometry.chamber_id_m
        and geometry.injector_face_diameter_m <= geometry.chamber_id_m * float(geometry_policy["max_injector_face_margin_factor"]),
        geometry.injector_face_diameter_m / geometry.chamber_id_m if geometry.chamber_id_m > 0.0 else math.inf,
        {
            "min_factor": 1.0,
            "max_factor": float(geometry_policy["max_injector_face_margin_factor"]),
        },
        "Injector face diameter should cover the chamber bore without excessive overhang.",
    )
    checks["nozzle_area_ratio_reasonable"] = _check(
        float(geometry_policy["min_nozzle_area_ratio"]) <= geometry.nozzle_area_ratio <= float(geometry_policy["max_nozzle_area_ratio"]),
        geometry.nozzle_area_ratio,
        {
            "min": float(geometry_policy["min_nozzle_area_ratio"]),
            "max": float(geometry_policy["max_nozzle_area_ratio"]),
        },
        "Nozzle area ratio is outside the configured first-pass range.",
    )
    checks["free_volume_positive"] = _check(
        geometry.free_volume_initial_m3 > 0.0 and geometry.free_volume_initial_m3 <= free_volume_envelope_m3,
        geometry.free_volume_initial_m3,
        {"min_m3": 0.0, "max_m3": free_volume_envelope_m3},
        "Initial chamber free volume must be positive and bounded by the chamber envelope.",
    )
    checks["chamber_to_throat_ratio"] = _check(
        float(geometry_policy["min_chamber_to_throat_diameter_ratio"])
        <= chamber_to_throat
        <= float(geometry_policy["max_chamber_to_throat_diameter_ratio"]),
        chamber_to_throat,
        {
            "min": float(geometry_policy["min_chamber_to_throat_diameter_ratio"]),
            "max": float(geometry_policy["max_chamber_to_throat_diameter_ratio"]),
        },
        "Chamber-to-throat diameter ratio is outside the configured sanity band.",
    )
    checks["port_to_throat_ratio"] = _check(
        float(geometry_policy["min_port_to_throat_diameter_ratio"])
        <= port_to_throat
        <= float(geometry_policy["max_port_to_throat_diameter_ratio"]),
        port_to_throat,
        {
            "min": float(geometry_policy["min_port_to_throat_diameter_ratio"]),
            "max": float(geometry_policy["max_port_to_throat_diameter_ratio"]),
        },
        "Initial port-to-throat diameter ratio is outside the configured sanity band.",
    )
    checks["baseline_port_architecture"] = _check(
        (not bool(geometry_policy["single_port_baseline"]) and geometry.port_count == int(geometry_policy["baseline_port_count"]))
        or (bool(geometry_policy["single_port_baseline"]) and geometry.port_count == 1),
        geometry.port_count,
        {
            "single_port_baseline": bool(geometry_policy["single_port_baseline"]),
            "baseline_port_count": int(geometry_policy["baseline_port_count"]),
        },
        "Frozen geometry no longer matches the intended baseline port architecture.",
    )

    lstar_in_band = float(geometry_policy["lstar_warning_min_m"]) <= geometry.lstar_initial_m <= float(geometry_policy["lstar_warning_max_m"])
    checks["lstar_soft_band"] = _check(
        lstar_in_band,
        geometry.lstar_initial_m,
        {
            "min_m": float(geometry_policy["lstar_warning_min_m"]),
            "max_m": float(geometry_policy["lstar_warning_max_m"]),
        },
        "Initial L* sits outside the configured soft warning band.",
        hard=not bool(geometry_policy["lstar_report_only"]),
    )

    if geometry.nominal_constraint_pass is not None:
        checks["nominal_constraints_pass"] = _check(
            bool(geometry.nominal_constraint_pass),
            geometry.nominal_constraint_pass,
            {"required": True},
            "Nominal Step 1 constraints did not all pass before geometry freeze.",
            hard=bool(geometry_policy["require_nominal_constraints_pass"]),
        )
    if geometry.corner_cases_all_pass is not None:
        checks["corner_constraints_pass"] = _check(
            bool(geometry.corner_cases_all_pass),
            geometry.corner_cases_all_pass,
            {"required": True},
            "One or more named Step 1 corner cases failed their constraints.",
            hard=bool(geometry_policy["require_corner_constraints_pass"]),
        )

    geometry_valid = all(check["passed"] for check in checks.values() if check["hard"])
    warnings = [f"{name}: {payload['note']}" for name, payload in checks.items() if not payload["passed"]]
    return checks, geometry_valid, warnings
