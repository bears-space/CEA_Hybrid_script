"""Fluid-property helpers for surrogate and oxidizer cold-flow modes."""

from __future__ import annotations

from typing import Any, Mapping

from src.coldflow.coldflow_types import ColdFlowDataset, ColdFlowPoint


def resolve_point_fluid_name(point: ColdFlowPoint, coldflow_config: Mapping[str, Any]) -> str:
    configured = str(coldflow_config.get("fluid", {}).get("name", "")).strip()
    return str(point.fluid_name or configured or "unspecified")


def resolve_point_density_kg_m3(point: ColdFlowPoint, coldflow_config: Mapping[str, Any]) -> float:
    if point.fluid_density_kg_m3 is not None:
        return float(point.fluid_density_kg_m3)
    configured_density = coldflow_config.get("fluid", {}).get("density_kg_m3")
    if configured_density is None:
        raise ValueError(
            f"Cold-flow point '{point.test_id}' is missing fluid density; "
            "provide point.fluid_density_kg_m3 or coldflow.fluid.density_kg_m3."
        )
    return float(configured_density)


def surrogate_fluid_warnings(dataset: ColdFlowDataset, coldflow_config: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    fluid_section = dict(coldflow_config.get("fluid", {}))
    if bool(fluid_section.get("is_surrogate", False)) or bool(dataset.rig_definition.surrogate_fluid_used):
        warnings.append(
            "Surrogate-fluid calibration is tagged for partial transfer only; do not assume direct injector or feed transfer to N2O without review."
        )
    intended_application = str(fluid_section.get("intended_application", "")).strip()
    if intended_application:
        warnings.append(f"Declared surrogate-fluid intended application: {intended_application}")
    return warnings
