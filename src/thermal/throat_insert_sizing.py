"""Optional thermal-protection placeholder sizing for liners and throat inserts."""

from __future__ import annotations

import math

from src.thermal.gas_side_htc import effective_gas_temperature_k, estimate_region_htc_history_w_m2k
from src.thermal.lumped_wall_model import round_up_thickness, simulate_two_node_wall
from src.thermal.thermal_resistance import effective_gas_side_htc_with_protection
from src.thermal.thermal_types import (
    ThermalDesignPolicy,
    ThermalLoadCase,
    ThermalMaterialDefinition,
    ThermalProtectionSizingResult,
)


def _allowable_temperature_k(material: ThermalMaterialDefinition, policy: ThermalDesignPolicy) -> float:
    if policy.temperature_limit_basis == "softening_temp" and material.melt_or_softening_temp_k is not None:
        basis = material.melt_or_softening_temp_k
    else:
        basis = material.max_service_temp_k
    if basis is None:
        raise ValueError(f"Thermal material '{material.material_name}' does not define the requested temperature basis.")
    return max(float(basis) - float(policy.service_temp_margin_k), 1.0)


def size_protection_layer(
    *,
    protection_name: str,
    protected_region: str,
    surface_area_m2: float,
    characteristic_diameter_m: float,
    base_wall_thickness_m: float,
    base_material: ThermalMaterialDefinition,
    protection_material: ThermalMaterialDefinition,
    load_case: ThermalLoadCase,
    policy: ThermalDesignPolicy,
    selected_initial_thickness_m: float,
    throat_multiplier: float,
    injector_face_multiplier: float,
    area_ratio: float,
) -> ThermalProtectionSizingResult:
    """Size a simple protection layer against the selected base-wall temperature limit."""

    allowable_k = _allowable_temperature_k(base_material, policy)
    htc_history = estimate_region_htc_history_w_m2k(
        region_name=protected_region,
        chamber_pressure_pa_time=load_case.chamber_pressure_pa_time,
        cstar_time=load_case.cstar_time,
        throat_diameter_m=math.sqrt(4.0 * load_case.throat_area_m2 / math.pi),
        area_ratio=area_ratio,
        gamma_time=load_case.gamma_time,
        throat_multiplier=throat_multiplier,
        injector_face_multiplier=injector_face_multiplier,
    )
    gas_temp_history = [
        effective_gas_temperature_k(protected_region, value, area_ratio=area_ratio)
        for value in load_case.chamber_temp_k_time
    ]

    def peak_inner_for(thickness_m: float) -> float:
        effective_htc = [
            effective_gas_side_htc_with_protection(
                gas_side_htc_w_m2k=h_value,
                protection_thickness_m=thickness_m,
                protection_conductivity_w_mk=protection_material.conductivity_w_mk,
            )
            for h_value in htc_history
        ]
        response = simulate_two_node_wall(
            time_s=load_case.time_s,
            gas_temperature_k=gas_temp_history,
            gas_side_htc_w_m2k=effective_htc,
            wall_thickness_m=base_wall_thickness_m,
            density_kg_m3=base_material.density_kg_m3,
            conductivity_w_mk=base_material.conductivity_w_mk,
            heat_capacity_j_kgk=base_material.heat_capacity_j_kgk,
            outer_h_w_m2k=policy.outer_h_guess_w_m2k,
            ambient_temp_k=policy.outer_ambient_temp_k,
            initial_temp_k=policy.outer_ambient_temp_k,
            emissivity=base_material.emissivity if base_material.emissivity is not None else policy.surface_emissivity,
            radiation_enabled=policy.radiation_enabled,
        )
        return max(response["inner_wall_temp_k"])

    required_thickness_m = 0.0
    selected_thickness_m = max(float(selected_initial_thickness_m), 0.0)
    reduced_peak_k = peak_inner_for(selected_thickness_m)
    warnings: list[str] = []

    if reduced_peak_k > allowable_k:
        for trial_index in range(1, 13):
            candidate = round_up_thickness(
                float(trial_index) * float(policy.minimum_protection_thickness_m),
                policy.thermal_roundup_increment_m,
                policy.minimum_protection_thickness_m,
            )
            candidate_peak_k = peak_inner_for(candidate)
            if candidate_peak_k <= allowable_k:
                required_thickness_m = candidate
                selected_thickness_m = max(selected_thickness_m, candidate)
                reduced_peak_k = candidate_peak_k
                break
        else:
            warnings.append(f"{protection_name}: protection thickness search did not restore the base wall below its limit.")
            required_thickness_m = round_up_thickness(
                12.0 * float(policy.minimum_protection_thickness_m),
                policy.thermal_roundup_increment_m,
                policy.minimum_protection_thickness_m,
            )
    mass_estimate_kg = float(surface_area_m2) * float(selected_thickness_m) * protection_material.density_kg_m3
    thermal_margin_k = allowable_k - reduced_peak_k
    return ThermalProtectionSizingResult(
        protection_name=protection_name,
        protected_region=protected_region,
        material_name=protection_material.material_name,
        required_thickness_m=required_thickness_m,
        selected_thickness_m=selected_thickness_m,
        mass_estimate_kg=mass_estimate_kg,
        reduced_peak_inner_wall_temp_k=reduced_peak_k,
        thermal_margin_k=thermal_margin_k,
        valid=thermal_margin_k >= 0.0,
        warnings=warnings,
        notes=[
            f"Characteristic diameter used for reporting: {characteristic_diameter_m:.4f} m.",
            "Protection layer modeled as added conduction resistance without recession or temperature-dependent properties.",
        ],
    )
