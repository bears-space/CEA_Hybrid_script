"""Material catalog and allowable-stress helpers for the structural workflow."""

from __future__ import annotations

from typing import Any, Mapping

from src.structural.structural_types import MaterialDefinition, StructuralDesignPolicy


def _base_material_catalog() -> dict[str, dict[str, Any]]:
    return {
        "aluminum_6061_t6": {
            "material_name": "aluminum_6061_t6",
            "density_kg_m3": 2700.0,
            "yield_strength_pa": 276.0e6,
            "ultimate_strength_pa": 310.0e6,
            "youngs_modulus_pa": 68.9e9,
            "poisson_ratio": 0.33,
            "max_service_temp_k": 423.0,
            "notes": ["Room-temperature first-pass allowables only."],
        },
        "aluminum_7075_t6": {
            "material_name": "aluminum_7075_t6",
            "density_kg_m3": 2810.0,
            "yield_strength_pa": 505.0e6,
            "ultimate_strength_pa": 572.0e6,
            "youngs_modulus_pa": 71.7e9,
            "poisson_ratio": 0.33,
            "max_service_temp_k": 393.0,
            "notes": ["Corrosion and elevated-temperature behavior are future refinements."],
        },
        "stainless_304": {
            "material_name": "stainless_304",
            "density_kg_m3": 8000.0,
            "yield_strength_pa": 215.0e6,
            "ultimate_strength_pa": 505.0e6,
            "youngs_modulus_pa": 193.0e9,
            "poisson_ratio": 0.29,
            "max_service_temp_k": 973.0,
            "notes": ["Annealed 304 placeholder values."],
        },
        "steel_4140_qt": {
            "material_name": "steel_4140_qt",
            "density_kg_m3": 7850.0,
            "yield_strength_pa": 655.0e6,
            "ultimate_strength_pa": 850.0e6,
            "youngs_modulus_pa": 205.0e9,
            "poisson_ratio": 0.29,
            "max_service_temp_k": 673.0,
            "notes": ["Generic quenched-and-tempered alloy-steel placeholder."],
        },
        "titanium_6al4v": {
            "material_name": "titanium_6al4v",
            "density_kg_m3": 4430.0,
            "yield_strength_pa": 880.0e6,
            "ultimate_strength_pa": 950.0e6,
            "youngs_modulus_pa": 114.0e9,
            "poisson_ratio": 0.34,
            "max_service_temp_k": 673.0,
            "notes": ["First-pass isotropic metal approximation only."],
        },
    }


def _allowable_stress_pa(
    material: Mapping[str, Any],
    policy: StructuralDesignPolicy,
    *,
    user_override_pa: float | None = None,
) -> float:
    if policy.allowable_basis == "yield_based":
        return float(material["yield_strength_pa"]) / float(policy.yield_safety_factor)
    if policy.allowable_basis == "ultimate_based":
        return float(material["ultimate_strength_pa"]) / float(policy.ultimate_safety_factor)
    if user_override_pa is None:
        user_override_pa = material.get("allowable_stress_pa")
    if user_override_pa is None:
        raise ValueError(
            f"Material '{material.get('material_name', 'unknown')}' needs allowable_stress_pa for allowable_basis='user_override'."
        )
    return float(user_override_pa)


def resolve_material_definition(
    material_name: str,
    structural_config: Mapping[str, Any],
    policy: StructuralDesignPolicy,
) -> MaterialDefinition:
    """Resolve a material name against the built-in catalog and optional config overrides."""

    material_key = str(material_name).strip().lower()
    custom_materials = dict(structural_config.get("custom_materials", {}))
    catalog = _base_material_catalog()
    raw_material = custom_materials.get(material_key, catalog.get(material_key))
    if raw_material is None:
        raise ValueError(f"Unknown structural material '{material_name}'.")
    material = dict(raw_material)
    allowable = _allowable_stress_pa(material, policy, user_override_pa=material.get("allowable_stress_pa"))
    return MaterialDefinition(
        material_name=str(material.get("material_name", material_key)),
        density_kg_m3=float(material["density_kg_m3"]),
        yield_strength_pa=float(material["yield_strength_pa"]),
        ultimate_strength_pa=float(material["ultimate_strength_pa"]),
        allowable_stress_pa=float(allowable),
        youngs_modulus_pa=float(material["youngs_modulus_pa"]) if material.get("youngs_modulus_pa") is not None else None,
        poisson_ratio=float(material["poisson_ratio"]) if material.get("poisson_ratio") is not None else None,
        max_service_temp_k=float(material["max_service_temp_k"]) if material.get("max_service_temp_k") is not None else None,
        notes=[str(item) for item in material.get("notes", [])],
    )
