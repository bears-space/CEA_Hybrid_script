"""Back-calculation from real injector geometry to reduced-order effective properties."""

from __future__ import annotations

from typing import Mapping

from src.injector_design.injector_types import InjectorEffectiveModel, InjectorGeometryDefinition


def estimate_discharge_coefficient(
    *,
    hole_ld_ratio: float,
    default_cd: float,
    edge_model: str,
    backcalculation_mode: str,
) -> tuple[float, list[str]]:
    """Estimate an effective discharge coefficient from simple edge and L/D heuristics."""

    notes: list[str] = []
    if backcalculation_mode == "constant_cd":
        notes.append(f"Using constant discharge coefficient Cd={default_cd:.3f}.")
        return float(default_cd), notes

    edge_base_cd = {
        "sharp_edged": 0.78,
        "chamfered": 0.84,
        "rounded": 0.90,
    }.get(edge_model, float(default_cd))
    ld_ratio = max(float(hole_ld_ratio), 1.0e-9)
    if ld_ratio < 0.5:
        ld_factor = 0.96
    elif ld_ratio <= 2.0:
        ld_factor = 1.0
    elif ld_ratio <= 4.0:
        ld_factor = 0.98
    else:
        ld_factor = max(0.90, 1.0 - 0.02 * (ld_ratio - 4.0))
    estimated_cd = max(min(edge_base_cd * ld_factor, 0.98), 0.10)
    notes.append(
        f"Estimated Cd from edge model '{edge_model}' with L/D={ld_ratio:.2f}; "
        f"base Cd={edge_base_cd:.3f}, L/D factor={ld_factor:.3f}."
    )
    return estimated_cd, notes


def estimate_effective_injector_from_geometry(
    injector_geometry: InjectorGeometryDefinition,
    fluid_state: Mapping[str, float] | None = None,
    discharge_model: Mapping[str, float | str] | None = None,
) -> InjectorEffectiveModel:
    """Return the reduced-order injector model implied by a real showerhead layout."""

    state = dict(fluid_state or {})
    discharge = dict(discharge_model or {})
    mdot_ox_kg_s = float(state.get("mdot_ox_kg_s", injector_geometry.design_mdot_ox_kg_s))
    liquid_density_kg_m3 = float(state.get("liquid_density_kg_m3", injector_geometry.design_liquid_density_kg_m3))
    chamber_pressure_pa = float(state.get("chamber_pressure_pa", injector_geometry.design_chamber_pressure_pa))
    default_cd = float(discharge.get("default_injector_cd", injector_geometry.estimated_cd))
    edge_model = str(discharge.get("discharge_edge_model", injector_geometry.discharge_edge_model))
    backcalculation_mode = str(discharge.get("backcalculation_mode", injector_geometry.backcalculation_mode))

    estimated_cd, notes = estimate_discharge_coefficient(
        hole_ld_ratio=injector_geometry.hole_ld_ratio,
        default_cd=default_cd,
        edge_model=edge_model,
        backcalculation_mode=backcalculation_mode,
    )
    total_geometric_area_m2 = float(injector_geometry.total_geometric_area_m2)
    effective_cda_m2 = estimated_cd * total_geometric_area_m2
    design_delta_p_pa = 0.0
    if mdot_ox_kg_s > 0.0 and effective_cda_m2 > 0.0 and liquid_density_kg_m3 > 0.0:
        design_delta_p_pa = (mdot_ox_kg_s / effective_cda_m2) ** 2 / (2.0 * liquid_density_kg_m3)
    design_inlet_pressure_pa = chamber_pressure_pa + design_delta_p_pa
    design_hole_velocity_m_s = 0.0
    if liquid_density_kg_m3 > 0.0 and total_geometric_area_m2 > 0.0:
        design_hole_velocity_m_s = mdot_ox_kg_s / (liquid_density_kg_m3 * total_geometric_area_m2)

    required_total_area_m2 = max(float(injector_geometry.required_total_area_m2), 1.0e-12)
    required_effective_cda_m2 = max(float(injector_geometry.required_effective_cda_m2), 1.0e-12)
    return InjectorEffectiveModel(
        discharge_model=backcalculation_mode,
        estimated_cd=estimated_cd,
        total_geometric_area_m2=total_geometric_area_m2,
        effective_area_m2=total_geometric_area_m2,
        effective_cda_m2=effective_cda_m2,
        design_mdot_ox_kg_s=mdot_ox_kg_s,
        design_delta_p_pa=design_delta_p_pa,
        design_injector_inlet_pressure_pa=design_inlet_pressure_pa,
        design_chamber_pressure_pa=chamber_pressure_pa,
        design_hole_velocity_m_s=design_hole_velocity_m_s,
        area_ratio_to_requirement=total_geometric_area_m2 / required_total_area_m2,
        cda_ratio_to_requirement=effective_cda_m2 / required_effective_cda_m2,
        notes=notes,
    )
