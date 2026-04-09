"""Stop-condition classification helpers for the modular 0D workflow."""

from __future__ import annotations

STOP_REASON_MESSAGES = {
    "burn_time_reached": "Target burn time reached.",
    "tank_quality_limit_exceeded": "Tank quality limit exceeded before the full burn time.",
    "port_radius_reached_outer_radius": "Fuel web was exhausted before the full burn time.",
    "tank_depleted": "Oxidizer mass depleted before the full burn time.",
    "solver_failure": "The 0D solver failed.",
}


def classify_stop_reason(stop_reason: str) -> tuple[str, list[str]]:
    if stop_reason == "burn_time_reached":
        return "completed", []
    if stop_reason in {
        "tank_quality_limit_exceeded",
        "port_radius_reached_outer_radius",
        "tank_depleted",
    }:
        return "completed", [STOP_REASON_MESSAGES[stop_reason]]
    return "failed", [STOP_REASON_MESSAGES.get(stop_reason, f"Unhandled stop reason: {stop_reason}")]
