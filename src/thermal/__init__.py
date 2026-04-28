"""First-pass thermal sizing package."""

from src.thermal.material_thermal_db import resolve_thermal_material_definition
from src.thermal.thermal_load_cases import build_thermal_load_cases
from src.thermal.thermal_types import (
    ChamberThermalResult,
    InjectorFaceThermalResult,
    NozzleThermalResult,
    RegionThermalResult,
    ThermalDesignPolicy,
    ThermalLoadCase,
    ThermalMaterialDefinition,
    ThermalProtectionSizingResult,
    ThermalSizingResult,
)
from src.thermal.workflow import merge_thermal_config, run_thermal_sizing_workflow

__all__ = [
    "ChamberThermalResult",
    "InjectorFaceThermalResult",
    "NozzleThermalResult",
    "RegionThermalResult",
    "ThermalDesignPolicy",
    "ThermalLoadCase",
    "ThermalMaterialDefinition",
    "ThermalProtectionSizingResult",
    "ThermalSizingResult",
    "build_thermal_load_cases",
    "merge_thermal_config",
    "resolve_thermal_material_definition",
    "run_thermal_sizing_workflow",
]
