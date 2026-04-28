"""Compatibility wrapper for the canonical config package."""

from src.config import (
    CornerCaseDefinition,
    DEFAULT_DESIGN_CONFIG,
    UncertaintySpec,
    build_design_config,
    load_design_config,
    normalize_cfd_config,
    normalize_coldflow_config,
    normalize_hydraulic_validation_config,
    normalize_nozzle_offdesign_config,
    normalize_structural_config,
    normalize_testing_config,
    normalize_thermal_config,
)

__all__ = [
    "CornerCaseDefinition",
    "DEFAULT_DESIGN_CONFIG",
    "UncertaintySpec",
    "build_design_config",
    "load_design_config",
    "normalize_cfd_config",
    "normalize_coldflow_config",
    "normalize_hydraulic_validation_config",
    "normalize_nozzle_offdesign_config",
    "normalize_structural_config",
    "normalize_testing_config",
    "normalize_thermal_config",
]
