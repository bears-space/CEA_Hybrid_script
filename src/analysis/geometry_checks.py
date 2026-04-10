"""Reusable geometry validity checks for first-pass hybrid grain sizing."""

from __future__ import annotations

from typing import Any, Mapping


def _check(passed: bool, value: Any, limit: Any, message: str) -> dict[str, Any]:
    return {
        "passed": bool(passed),
        "value": value,
        "limit": limit,
        "message": message,
    }


def evaluate_grain_geometry(
    *,
    port_radius_initial_m: float,
    grain_outer_radius_m: float | None,
    grain_length_m: float,
    port_count: int,
    min_radial_web_m: float,
    min_burnout_web_m: float | None = None,
    web_remaining_final_m: float | None = None,
    max_port_to_outer_radius_ratio: float = 0.95,
    max_grain_slenderness_ratio: float = 18.0,
) -> dict[str, Any]:
    if grain_outer_radius_m is None:
        return {
            "valid": False,
            "checks": {
                "outer_radius_defined": _check(False, None, "> 0", "Outer radius must be defined for geometry validation."),
            },
            "warnings": ["Outer radius must be defined for geometry validation."],
            "suggestions": ["Set or derive a positive grain outer radius."],
        }

    radial_web_m = float(grain_outer_radius_m) - float(port_radius_initial_m)
    port_to_outer_ratio = float(port_radius_initial_m) / float(grain_outer_radius_m)
    grain_slenderness_ratio = float(grain_length_m) / (2.0 * float(grain_outer_radius_m))

    checks = {
        "outer_radius_gt_port_radius": _check(
            grain_outer_radius_m > port_radius_initial_m,
            radial_web_m,
            "> 0 m",
            "Outer radius must exceed the initial port radius.",
        ),
        "minimum_initial_web": _check(
            radial_web_m >= float(min_radial_web_m),
            radial_web_m,
            {"min_m": float(min_radial_web_m)},
            "Initial radial web is below the configured minimum margin.",
        ),
        "maximum_port_to_outer_ratio": _check(
            port_to_outer_ratio <= float(max_port_to_outer_radius_ratio),
            port_to_outer_ratio,
            {"max": float(max_port_to_outer_radius_ratio)},
            "Initial port radius is too close to the outer grain radius.",
        ),
        "maximum_grain_slenderness": _check(
            grain_slenderness_ratio <= float(max_grain_slenderness_ratio),
            grain_slenderness_ratio,
            {"max": float(max_grain_slenderness_ratio)},
            "Grain length to diameter ratio is too large for a robust first-pass single-port grain.",
        ),
        "single_port_baseline": _check(
            int(port_count) == 1,
            int(port_count),
            {"required": 1},
            "Current baseline assumptions only support a single-port geometry.",
        ),
    }
    if min_burnout_web_m is not None and web_remaining_final_m is not None:
        checks["minimum_final_web"] = _check(
            float(web_remaining_final_m) >= float(min_burnout_web_m),
            float(web_remaining_final_m),
            {"min_m": float(min_burnout_web_m)},
            "Remaining web at the end of the simulated burn is below the configured burnout margin.",
        )

    warnings = [payload["message"] for payload in checks.values() if not payload["passed"]]
    suggestions: list[str] = []
    if not checks["minimum_initial_web"]["passed"]:
        suggestions.append("Increase grain outer radius or reduce initial port radius to recover radial web.")
    if not checks["maximum_port_to_outer_ratio"]["passed"]:
        suggestions.append("Reduce target initial Gox, increase outer radius, or add port area more deliberately.")
    if not checks["maximum_grain_slenderness"]["passed"]:
        suggestions.append("Reduce burn time, increase outer radius, or move away from a very slender single-port grain.")
    if "minimum_final_web" in checks and not checks["minimum_final_web"]["passed"]:
        suggestions.append("Reduce burn time, reduce regression rate, or add web thickness to preserve burnout margin.")
    if not checks["single_port_baseline"]["passed"]:
        suggestions.append("Keep a single-port baseline here or update the architecture assumptions before using multiple ports.")

    return {
        "valid": all(payload["passed"] for payload in checks.values()),
        "checks": checks,
        "warnings": warnings,
        "suggestions": suggestions,
        "radial_web_m": radial_web_m,
        "port_to_outer_radius_ratio": port_to_outer_ratio,
        "grain_slenderness_ratio": grain_slenderness_ratio,
    }

