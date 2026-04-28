"""Reduced-order injector-face thermal evaluation."""

from __future__ import annotations

import math

from src.injector_design.injector_types import InjectorGeometryDefinition
from src.thermal.gas_side_htc import effective_gas_temperature_k, estimate_region_htc_history_w_m2k
from src.thermal.lumped_wall_model import simulate_two_node_wall
from src.thermal.thermal_types import (
    InjectorFaceThermalResult,
    RegionThermalResult,
    ThermalDesignPolicy,
    ThermalLoadCase,
    ThermalMaterialDefinition,
)


def _allowable_temperature_k(material: ThermalMaterialDefinition, policy: ThermalDesignPolicy) -> float:
    if policy.temperature_limit_basis == "softening_temp" and material.melt_or_softening_temp_k is not None:
        basis = material.melt_or_softening_temp_k
    else:
        basis = material.max_service_temp_k
    if basis is None:
        raise ValueError(f"Thermal material '{material.material_name}' does not define the requested temperature basis.")
    return max(float(basis) - float(policy.service_temp_margin_k), 1.0)


def evaluate_injector_face(
    *,
    active_face_diameter_m: float,
    plate_thickness_m: float,
    load_case: ThermalLoadCase,
    material: ThermalMaterialDefinition,
    policy: ThermalDesignPolicy,
    injector_geometry: InjectorGeometryDefinition | None = None,
    structural_plate_thickness_m: float | None = None,
) -> InjectorFaceThermalResult:
    """Evaluate a first-pass injector-face thermal response."""

    gas_temperature_history_k = [
        effective_gas_temperature_k("injector_face", value)
        for value in load_case.chamber_temp_k_time
    ]
    htc_history_w_m2k = estimate_region_htc_history_w_m2k(
        region_name="injector_face",
        chamber_pressure_pa_time=load_case.chamber_pressure_pa_time,
        cstar_time=load_case.cstar_time,
        throat_diameter_m=math.sqrt(4.0 * load_case.throat_area_m2 / math.pi),
        area_ratio=load_case.area_ratio,
        gamma_time=load_case.gamma_time,
        throat_multiplier=policy.throat_htc_multiplier,
        injector_face_multiplier=policy.injector_face_htc_multiplier,
    )
    wall_result = simulate_two_node_wall(
        time_s=load_case.time_s,
        gas_temperature_k=gas_temperature_history_k,
        gas_side_htc_w_m2k=htc_history_w_m2k,
        wall_thickness_m=plate_thickness_m,
        density_kg_m3=material.density_kg_m3,
        conductivity_w_mk=material.conductivity_w_mk,
        heat_capacity_j_kgk=material.heat_capacity_j_kgk,
        outer_h_w_m2k=policy.outer_h_guess_w_m2k,
        ambient_temp_k=policy.outer_ambient_temp_k,
        initial_temp_k=policy.outer_ambient_temp_k,
        emissivity=material.emissivity if material.emissivity is not None else policy.surface_emissivity,
        radiation_enabled=policy.radiation_enabled,
    )
    inner_history = list(wall_result["inner_wall_temp_k"])
    outer_history = list(wall_result["outer_wall_temp_k"])
    heat_flux_history = list(wall_result["heat_flux_w_m2"])
    peak_inner = max(inner_history)
    peak_index = inner_history.index(peak_inner)
    allowable_k = _allowable_temperature_k(material, policy)
    open_area_ratio = injector_geometry.geometric_open_area_ratio if injector_geometry is not None else None
    warnings: list[str] = []
    if open_area_ratio is not None and open_area_ratio > 0.3:
        warnings.append("injector_face: high open-area ratio may reduce thermal conduction paths and needs later local analysis.")
    if structural_plate_thickness_m is not None and abs(structural_plate_thickness_m - plate_thickness_m) / max(plate_thickness_m, 1.0e-9) > 0.25:
        warnings.append("injector_face: thermal and structural plate-thickness assumptions differ materially.")
    if wall_result["peak_biot_number"] > 0.1:
        warnings.append("injector_face: lumped wall assumption is outside the usual Biot <= 0.1 range.")
    if peak_inner > allowable_k:
        warnings.append("injector_face: peak inner-wall temperature exceeds the selected allowable temperature basis.")
    region = RegionThermalResult(
        region_name="injector_face",
        material_name=material.material_name,
        selected_wall_thickness_m=float(plate_thickness_m),
        peak_heat_flux_w_m2=max(heat_flux_history),
        peak_inner_wall_temp_k=peak_inner,
        peak_outer_wall_temp_k=max(outer_history),
        max_allowable_temp_k=allowable_k,
        thermal_margin_k=allowable_k - peak_inner,
        governing_time_s=float(load_case.time_s[peak_index]),
        wall_biot_number_peak=float(wall_result["peak_biot_number"]),
        valid=peak_inner <= allowable_k,
        time_history_s=list(load_case.time_s),
        gas_side_htc_history_w_m2k=htc_history_w_m2k,
        heat_flux_history_w_m2=heat_flux_history,
        inner_wall_temp_history_k=inner_history,
        outer_wall_temp_history_k=outer_history,
        model_assumptions=[
            "Injector-face heat transfer uses a configurable multiplier relative to the chamber Bartz-like placeholder.",
            "No local jet-impingement CFD or manifold conduction model is included.",
        ],
        warnings=warnings,
    )
    return InjectorFaceThermalResult(
        region=region,
        active_face_diameter_m=float(active_face_diameter_m),
        open_area_ratio=open_area_ratio,
    )
