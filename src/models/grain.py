"""Thin wrappers over the legacy hybrid grain helper functions."""

from blowdown_hybrid.grain import fuel_mass_flow_kg_s, regression_rate_m_s, required_grain_length_for_target_fuel_flow, total_port_area_m2

__all__ = [
    "fuel_mass_flow_kg_s",
    "regression_rate_m_s",
    "required_grain_length_for_target_fuel_flow",
    "total_port_area_m2",
]
