"""Stop-condition classification helpers for the modular 0D workflow."""

from __future__ import annotations

STOP_REASON_MESSAGES = {
    "burn_time_reached": "Target burn time reached.",
    "tank_quality_limit_exceeded": "Tank quality limit exceeded before the full burn time.",
    "port_radius_reached_outer_radius": "Fuel web was exhausted before the full burn time.",
    "grain_burnthrough": "A local axial cell reached the grain outer radius before the full burn time.",
    "tank_depleted": "Oxidizer mass depleted before the full burn time.",
    "usable_oxidizer_reserve_reached": "Configured oxidizer reserve was reached before the full burn time.",
    "tank_left_two_phase_region": "The oxidizer tank left the supported saturated two-phase model before the full burn time.",
    "flow_stopped": "Oxidizer flow collapsed to zero before the full burn time.",
    "port_growth_step_limit_exceeded": "The 1D solver timestep was too large for stable port-growth marching.",
    "non_finite_state": "The 1D solver reached a non-finite state.",
    "non_physical_state": "The 1D solver reached a non-physical state.",
    "solver_failure": "The 0D solver failed.",
}


def classify_stop_reason(stop_reason: str) -> tuple[str, list[str]]:
    if stop_reason == "burn_time_reached":
        return "completed", []
    if stop_reason in {
        "tank_quality_limit_exceeded",
        "port_radius_reached_outer_radius",
        "grain_burnthrough",
        "tank_depleted",
        "usable_oxidizer_reserve_reached",
        "tank_left_two_phase_region",
        "flow_stopped",
    }:
        return "completed", [STOP_REASON_MESSAGES[stop_reason]]
    return "failed", [STOP_REASON_MESSAGES.get(stop_reason, f"Unhandled stop reason: {stop_reason}")]
