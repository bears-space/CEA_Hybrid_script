"""Pressure-budget helpers shared by first-pass sizing and transient post-processing."""

from __future__ import annotations

from typing import Any


def safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0.0:
        return float("nan")
    return float(numerator) / float(denominator)


def pressure_budget(
    tank_pressure_pa: float,
    feed_pressure_drop_pa: float,
    injector_inlet_pressure_pa: float,
    injector_delta_p_pa: float,
    chamber_pressure_pa: float,
) -> dict[str, Any]:
    total_pressure_drop_pa = float(feed_pressure_drop_pa) + float(injector_delta_p_pa)
    return {
        "tank_pressure_pa": float(tank_pressure_pa),
        "feed_pressure_drop_pa": float(feed_pressure_drop_pa),
        "injector_inlet_pressure_pa": float(injector_inlet_pressure_pa),
        "injector_delta_p_pa": float(injector_delta_p_pa),
        "chamber_pressure_pa": float(chamber_pressure_pa),
        "total_pressure_drop_pa": total_pressure_drop_pa,
        "dp_feed_over_pc": safe_ratio(feed_pressure_drop_pa, chamber_pressure_pa),
        "dp_injector_over_pc": safe_ratio(injector_delta_p_pa, chamber_pressure_pa),
        "dp_total_over_ptank": safe_ratio(total_pressure_drop_pa, tank_pressure_pa),
        "injector_to_feed_dp_ratio": safe_ratio(injector_delta_p_pa, feed_pressure_drop_pa),
    }

