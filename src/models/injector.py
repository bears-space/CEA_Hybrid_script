"""Thin wrappers over the legacy injector and feed helper functions."""

from blowdown_hybrid.hydraulics import (
    equivalent_hole_diameter,
    feed_pressure_drop_pa,
    injector_mdot_kg_s,
    size_injector_total_area,
)

__all__ = [
    "equivalent_hole_diameter",
    "feed_pressure_drop_pa",
    "injector_mdot_kg_s",
    "size_injector_total_area",
]
