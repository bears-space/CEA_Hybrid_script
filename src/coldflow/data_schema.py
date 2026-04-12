"""Schema helpers for cold-flow CSV and JSON ingestion."""

from __future__ import annotations

from typing import Any, Iterable


UNIT_MULTIPLIERS = {
    "pa": 1.0,
    "kpa": 1.0e3,
    "mpa": 1.0e6,
    "bar": 1.0e5,
    "kg_s": 1.0,
    "g_s": 1.0e-3,
    "kg_m3": 1.0,
    "g_cc": 1.0e3,
    "k": 1.0,
    "c": (1.0, 273.15),
}


FIELD_ALIASES: dict[str, tuple[tuple[str, float | tuple[float, float]], ...]] = {
    "test_id": (("test_id", 1.0), ("test", 1.0), ("id", 1.0)),
    "point_index": (("point_index", 1.0), ("point", 1.0), ("index", 1.0)),
    "timestamp": (("timestamp", 1.0), ("time", 1.0), ("datetime", 1.0)),
    "fluid_name": (("fluid_name", 1.0), ("fluid", 1.0)),
    "fluid_temperature_k": (
        ("fluid_temperature_k", 1.0),
        ("temperature_k", 1.0),
        ("temp_k", 1.0),
        ("temperature_c", UNIT_MULTIPLIERS["c"]),
    ),
    "fluid_density_kg_m3": (
        ("fluid_density_kg_m3", 1.0),
        ("density_kg_m3", 1.0),
        ("rho_kg_m3", 1.0),
        ("density_g_cc", UNIT_MULTIPLIERS["g_cc"]),
    ),
    "upstream_pressure_pa": (
        ("upstream_pressure_pa", 1.0),
        ("upstream_pressure_bar", UNIT_MULTIPLIERS["bar"]),
        ("supply_pressure_pa", 1.0),
        ("supply_pressure_bar", UNIT_MULTIPLIERS["bar"]),
        ("tank_pressure_pa", 1.0),
        ("tank_pressure_bar", UNIT_MULTIPLIERS["bar"]),
    ),
    "injector_inlet_pressure_pa": (
        ("injector_inlet_pressure_pa", 1.0),
        ("injector_inlet_pressure_bar", UNIT_MULTIPLIERS["bar"]),
        ("p_inj_in_pa", 1.0),
        ("p_inj_in_bar", UNIT_MULTIPLIERS["bar"]),
    ),
    "downstream_pressure_pa": (
        ("downstream_pressure_pa", 1.0),
        ("downstream_pressure_bar", UNIT_MULTIPLIERS["bar"]),
        ("chamber_pressure_pa", 1.0),
        ("chamber_pressure_bar", UNIT_MULTIPLIERS["bar"]),
        ("back_pressure_pa", 1.0),
        ("back_pressure_bar", UNIT_MULTIPLIERS["bar"]),
    ),
    "measured_delta_p_feed_pa": (
        ("measured_delta_p_feed_pa", 1.0),
        ("delta_p_feed_pa", 1.0),
        ("dp_feed_pa", 1.0),
        ("delta_p_feed_bar", UNIT_MULTIPLIERS["bar"]),
        ("dp_feed_bar", UNIT_MULTIPLIERS["bar"]),
    ),
    "measured_delta_p_injector_pa": (
        ("measured_delta_p_injector_pa", 1.0),
        ("delta_p_injector_pa", 1.0),
        ("dp_injector_pa", 1.0),
        ("dp_inj_pa", 1.0),
        ("delta_p_injector_bar", UNIT_MULTIPLIERS["bar"]),
        ("dp_injector_bar", UNIT_MULTIPLIERS["bar"]),
        ("dp_inj_bar", UNIT_MULTIPLIERS["bar"]),
    ),
    "measured_mdot_kg_s": (
        ("measured_mdot_kg_s", 1.0),
        ("measured_mdot_g_s", UNIT_MULTIPLIERS["g_s"]),
        ("mdot_kg_s", 1.0),
        ("mdot_g_s", UNIT_MULTIPLIERS["g_s"]),
        ("mass_flow_kg_s", 1.0),
        ("mass_flow_g_s", UNIT_MULTIPLIERS["g_s"]),
    ),
    "notes": (("notes", 1.0), ("comment", 1.0)),
}


OPTIONAL_POINT_FIELDS = {
    "test_id",
    "point_index",
    "timestamp",
    "fluid_name",
    "fluid_temperature_k",
    "fluid_density_kg_m3",
    "upstream_pressure_pa",
    "injector_inlet_pressure_pa",
    "downstream_pressure_pa",
    "measured_delta_p_feed_pa",
    "measured_delta_p_injector_pa",
    "measured_mdot_kg_s",
    "notes",
}


def normalize_column_name(value: str) -> str:
    return str(value).strip().lower()


def apply_unit_scale(value: Any, scale: float | tuple[float, float]) -> float:
    numeric = float(value)
    if isinstance(scale, tuple):
        multiplier, offset = scale
        return numeric * multiplier + offset
    return numeric * float(scale)


def configured_aliases(configured: Iterable[str] | None) -> tuple[tuple[str, float], ...]:
    aliases = [normalize_column_name(value) for value in configured or [] if str(value).strip()]
    return tuple((alias, 1.0) for alias in aliases)
