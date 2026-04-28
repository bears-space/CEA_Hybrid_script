"""Boundary-condition package generation for external CFD cases."""

from __future__ import annotations

from typing import Any, Mapping

from src.cfd.cfd_types import CfdBoundaryConditionPackage, CfdOperatingPoint, CfdTargetDefinition


def _species_for_target(target: CfdTargetDefinition, operating_point: CfdOperatingPoint) -> list[dict[str, Any]]:
    if target.recommended_flow_type in {"cold_flow", "nonreacting"}:
        return [
            {
                "name": "oxidizer_surrogate",
                "model": "single-fluid nonreacting placeholder",
                "reference": operating_point.fluid_properties_reference,
            }
        ]
    if target.recommended_flow_type == "compressible":
        return [
            {
                "name": "equilibrium_gas_surrogate",
                "model": "single-species compressible placeholder",
                "reference": operating_point.fluid_properties_reference,
            }
        ]
    return [
        {
            "name": "hybrid_reacting_placeholder",
            "model": "reacting-mixture placeholder",
            "reference": operating_point.fluid_properties_reference,
        }
    ]


def build_cfd_boundary_conditions(
    target: CfdTargetDefinition,
    operating_point: CfdOperatingPoint,
    cfd_config: Mapping[str, Any],
) -> CfdBoundaryConditionPackage:
    """Build a CFD-ready boundary-condition summary from one operating point."""

    turbulence = {
        "model": str(cfd_config.get("turbulence_model", "sst_k_omega_placeholder")),
        "wall_treatment": str(cfd_config.get("wall_treatment", "automatic_placeholder")),
    }
    wall_assumptions = {
        "velocity": "no_slip",
        "roughness": "smooth_wall_placeholder",
        "thermal": (
            "adiabatic"
            if target.target_category in {"injector_plenum", "headend_prechamber"}
            else "adiabatic_or_prescribed_wall_temperature_placeholder"
        ),
    }
    symmetry = {
        "allowed": bool(cfd_config.get("geometry_simplifications", {}).get("allow_periodic_sector_model", False)),
        "note": "Apply symmetry only if the injector-hole pattern and objective support it.",
    }
    thermal_placeholders = {
        "wall_condition": wall_assumptions["thermal"],
        "reference_wall_temp_k": (
            None
            if operating_point.chamber_temp_k is None
            else max(float(operating_point.chamber_temp_k) - 800.0, 300.0)
        ),
    }
    case_name = f"{target.target_name}_{operating_point.operating_point_name}"

    if target.target_category == "injector_plenum":
        inlet_definitions = [
            {
                "name": "plenum_inlet",
                "type": "pressure_or_massflow_inlet",
                "total_pressure_pa": operating_point.injector_inlet_pressure_pa,
                "mass_flow_kg_s": operating_point.oxidizer_mass_flow_kg_s,
            }
        ]
        outlet_definitions = [
            {
                "name": "injector_discharge_outlet",
                "type": "static_pressure_outlet",
                "static_pressure_pa": operating_point.chamber_pressure_pa,
            }
        ]
    elif target.target_category == "headend_prechamber":
        inlet_definitions = [
            {
                "name": "injector_hole_inlet",
                "type": "massflow_or_velocity_inlet",
                "mass_flow_kg_s": operating_point.oxidizer_mass_flow_kg_s,
                "total_pressure_pa": operating_point.injector_inlet_pressure_pa,
            }
        ]
        outlet_definitions = [
            {
                "name": "grain_entrance_or_port_outlet",
                "type": "static_pressure_outlet",
                "static_pressure_pa": operating_point.chamber_pressure_pa,
            }
        ]
    elif target.target_category == "nozzle_local":
        inlet_definitions = [
            {
                "name": "nozzle_inlet",
                "type": "total_pressure_total_temperature_inlet",
                "total_pressure_pa": operating_point.chamber_pressure_pa,
                "total_temperature_k": operating_point.chamber_temp_k,
                "mass_flow_kg_s": operating_point.mass_flow_kg_s,
            }
        ]
        outlet_definitions = [
            {
                "name": "nozzle_exit",
                "type": "ambient_pressure_outlet",
                "static_pressure_pa": operating_point.ambient_pressure_pa,
            }
        ]
    else:
        inlet_definitions = [
            {
                "name": "oxidizer_inlet",
                "type": "massflow_or_total_pressure_inlet",
                "mass_flow_kg_s": operating_point.oxidizer_mass_flow_kg_s,
                "total_pressure_pa": operating_point.injector_inlet_pressure_pa,
            }
        ]
        outlet_definitions = [
            {
                "name": "internal_exit",
                "type": "pressure_outlet_placeholder",
                "static_pressure_pa": operating_point.chamber_pressure_pa,
            }
        ]
        thermal_placeholders["fuel_surface_model"] = "wall_mass_addition_or_reacting_boundary_placeholder"

    validity_flags = {
        "inlet_defined": bool(inlet_definitions),
        "outlet_defined": bool(outlet_definitions),
        "pressure_or_massflow_available": any(
            entry.get("total_pressure_pa") is not None or entry.get("mass_flow_kg_s") is not None
            for entry in inlet_definitions
        ),
        "downstream_pressure_available": any(entry.get("static_pressure_pa") is not None for entry in outlet_definitions),
    }
    notes = [
        "Boundary conditions are reduced-order placeholders intended for external CFD setup, not automated solver execution.",
        f"Recommended flow type: {target.recommended_flow_type}.",
    ]
    return CfdBoundaryConditionPackage(
        case_name=case_name,
        inlet_definitions=inlet_definitions,
        outlet_definitions=outlet_definitions,
        wall_assumptions=wall_assumptions,
        symmetry_assumptions=symmetry,
        turbulence_placeholder_settings=turbulence,
        thermal_bc_placeholders=thermal_placeholders,
        species_definitions=_species_for_target(target, operating_point),
        notes=notes,
        validity_flags=validity_flags,
    )
