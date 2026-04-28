"""Injector helpers spanning the legacy equivalent model and design synthesis."""

from src.blowdown_hybrid.hydraulics import (
    equivalent_hole_diameter,
    feed_pressure_drop_pa,
    injector_mdot_kg_s,
    size_injector_total_area,
)
from src.injector_design import (
    apply_injector_geometry_to_runtime,
    build_injector_synthesis_case,
    estimate_effective_injector_from_geometry,
    synthesize_showerhead_injector,
)

__all__ = [
    "apply_injector_geometry_to_runtime",
    "build_injector_synthesis_case",
    "estimate_effective_injector_from_geometry",
    "equivalent_hole_diameter",
    "feed_pressure_drop_pa",
    "injector_mdot_kg_s",
    "size_injector_total_area",
    "synthesize_showerhead_injector",
]

