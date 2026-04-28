"""Thermal material catalog and resolution helpers."""

from __future__ import annotations

from typing import Any, Mapping

from src.thermal.thermal_types import ThermalDesignPolicy, ThermalMaterialDefinition


def _base_material_catalog() -> dict[str, dict[str, Any]]:
    return {
        "aluminum_6061_t6": {
            "material_name": "aluminum_6061_t6",
            "density_kg_m3": 2700.0,
            "conductivity_w_mk": 167.0,
            "heat_capacity_j_kgk": 896.0,
            "emissivity": 0.2,
            "max_service_temp_k": 423.0,
            "melt_or_softening_temp_k": 855.0,
            "notes": ["Room-temperature first-pass thermal properties only."],
        },
        "aluminum_7075_t6": {
            "material_name": "aluminum_7075_t6",
            "density_kg_m3": 2810.0,
            "conductivity_w_mk": 130.0,
            "heat_capacity_j_kgk": 960.0,
            "emissivity": 0.2,
            "max_service_temp_k": 393.0,
            "melt_or_softening_temp_k": 750.0,
            "notes": ["Elevated-temperature derating is a later refinement."],
        },
        "stainless_304": {
            "material_name": "stainless_304",
            "density_kg_m3": 8000.0,
            "conductivity_w_mk": 16.2,
            "heat_capacity_j_kgk": 500.0,
            "emissivity": 0.55,
            "max_service_temp_k": 973.0,
            "melt_or_softening_temp_k": 1670.0,
            "notes": ["Annealed placeholder values."],
        },
        "steel_4140_qt": {
            "material_name": "steel_4140_qt",
            "density_kg_m3": 7850.0,
            "conductivity_w_mk": 42.0,
            "heat_capacity_j_kgk": 477.0,
            "emissivity": 0.6,
            "max_service_temp_k": 673.0,
            "melt_or_softening_temp_k": 1700.0,
            "notes": ["Generic quenched-and-tempered steel placeholder."],
        },
        "titanium_6al4v": {
            "material_name": "titanium_6al4v",
            "density_kg_m3": 4430.0,
            "conductivity_w_mk": 6.7,
            "heat_capacity_j_kgk": 560.0,
            "emissivity": 0.4,
            "max_service_temp_k": 673.0,
            "melt_or_softening_temp_k": 1878.0,
            "notes": ["First-pass isotropic metal approximation only."],
        },
        "graphite": {
            "material_name": "graphite",
            "density_kg_m3": 1750.0,
            "conductivity_w_mk": 90.0,
            "heat_capacity_j_kgk": 710.0,
            "emissivity": 0.8,
            "max_service_temp_k": 3200.0,
            "melt_or_softening_temp_k": 3650.0,
            "notes": ["Generic throat-insert placeholder."],
        },
        "phenolic_liner": {
            "material_name": "phenolic_liner",
            "density_kg_m3": 1350.0,
            "conductivity_w_mk": 0.25,
            "heat_capacity_j_kgk": 1250.0,
            "emissivity": 0.85,
            "max_service_temp_k": 650.0,
            "melt_or_softening_temp_k": 700.0,
            "notes": ["Ablative recession is not modeled in this first-pass layer."],
        },
    }


def resolve_thermal_material_definition(
    material_name: str,
    thermal_config: Mapping[str, Any],
    policy: ThermalDesignPolicy,
) -> ThermalMaterialDefinition:
    """Resolve a thermal material name against built-in and config-defined properties."""

    del policy  # Reserved for future temperature-basis-specific material resolution.

    material_key = str(material_name).strip().lower()
    custom_materials = dict(thermal_config.get("custom_materials", {}))
    catalog = _base_material_catalog()
    raw_material = custom_materials.get(material_key, catalog.get(material_key))
    if raw_material is None:
        raise ValueError(f"Unknown thermal material '{material_name}'.")
    material = dict(raw_material)
    density_kg_m3 = float(material["density_kg_m3"])
    conductivity_w_mk = float(material["conductivity_w_mk"])
    heat_capacity_j_kgk = float(material["heat_capacity_j_kgk"])
    diffusivity_m2_s = conductivity_w_mk / max(density_kg_m3 * heat_capacity_j_kgk, 1.0e-9)
    return ThermalMaterialDefinition(
        material_name=str(material.get("material_name", material_key)),
        density_kg_m3=density_kg_m3,
        conductivity_w_mk=conductivity_w_mk,
        heat_capacity_j_kgk=heat_capacity_j_kgk,
        diffusivity_m2_s=diffusivity_m2_s,
        emissivity=float(material["emissivity"]) if material.get("emissivity") is not None else None,
        max_service_temp_k=float(material["max_service_temp_k"]) if material.get("max_service_temp_k") is not None else None,
        melt_or_softening_temp_k=(
            float(material["melt_or_softening_temp_k"])
            if material.get("melt_or_softening_temp_k") is not None
            else None
        ),
        notes=[str(item) for item in material.get("notes", [])],
    )
