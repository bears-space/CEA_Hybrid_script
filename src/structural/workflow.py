"""High-level structural sizing workflow orchestration."""

from __future__ import annotations

from typing import Any, Mapping

from src.injector_design.injector_types import InjectorGeometryDefinition
from src.io_utils import deep_merge
from src.sizing.engine_state import EngineState, update_engine_state_validity
from src.sizing.geometry_types import GeometryDefinition
from src.structural.closure_sizing import size_closure
from src.structural.fastener_sizing import size_fasteners
from src.structural.grain_support import evaluate_grain_support
from src.structural.injector_plate_sizing import size_injector_plate
from src.structural.load_cases import build_structural_load_cases
from src.structural.material_db import resolve_material_definition
from src.structural.nozzle_mount_sizing import size_nozzle_mount
from src.structural.pressure_vessel import size_chamber_wall
from src.structural.structural_checks import build_validity_flags, collect_structural_warnings
from src.structural.structural_export import write_structural_outputs
from src.structural.structural_mass import estimate_structural_mass_breakdown
from src.structural.structural_types import StructuralDesignPolicy, StructuralSizingResult


def merge_structural_config(
    study_config: Mapping[str, Any],
    override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the structural config section after applying optional overrides."""

    override_section = dict(override or {})
    if "structural" in override_section and isinstance(override_section["structural"], Mapping):
        override_section = dict(override_section["structural"])
    return deep_merge(dict(study_config.get("structural", {})), override_section)


def _design_policy(structural_config: Mapping[str, Any]) -> StructuralDesignPolicy:
    policy = dict(structural_config.get("design_policy", {}))
    return StructuralDesignPolicy(
        allowable_basis=str(structural_config.get("allowable_basis", "yield_based")),
        yield_safety_factor=float(policy["yield_safety_factor"]),
        ultimate_safety_factor=float(policy["ultimate_safety_factor"]),
        proof_factor=float(policy["proof_factor"]),
        burst_factor=float(policy["burst_factor"]),
        thin_wall_switch_ratio=float(policy["thin_wall_switch_ratio"]),
        minimum_wall_thickness_m=float(policy["minimum_wall_thickness_m"]),
        minimum_flange_thickness_m=float(policy["minimum_flange_thickness_m"]),
        thickness_roundup_increment_m=float(policy["thickness_roundup_increment_m"]),
        default_bolt_preload_fraction=float(policy["default_bolt_preload_fraction"]),
        closure_model_type=str(policy["closure_model_type"]),
        injector_plate_model_type=str(policy["injector_plate_model_type"]),
        nozzle_mount_model_type=str(policy["nozzle_mount_model_type"]),
        mass_roundup_factor=float(policy["mass_roundup_factor"]),
        corrosion_or_manufacturing_allowance_m=float(policy["corrosion_or_manufacturing_allowance_m"]),
        closure_style=str(structural_config.get("closure_style", "bolted_flange")),
    )


def run_structural_sizing_workflow(
    study_config: Mapping[str, Any],
    structural_config: Mapping[str, Any],
    output_dir: str,
    *,
    geometry: GeometryDefinition,
    nominal_payload: Mapping[str, Any],
    injector_geometry: InjectorGeometryDefinition | None = None,
    corner_payload: Mapping[str, Any] | None = None,
    ballistics_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run first-pass structural sizing and export the standard output bundle."""

    canonical_state = EngineState.from_mapping(geometry.engine_state) if geometry.engine_state else None
    policy = _design_policy(structural_config)
    materials = {
        component: resolve_material_definition(material_name, structural_config, policy)
        for component, material_name in dict(structural_config.get("component_materials", {})).items()
    }
    load_cases, governing_load_case, warnings = build_structural_load_cases(
        structural_config,
        geometry,
        nominal_payload=nominal_payload,
        corner_payload=corner_payload,
        ballistics_payload=ballistics_payload,
    )
    chamber_inner_diameter_m = (
        2.0 * float(canonical_state.geometry.shell_inner_radius_m)
        if canonical_state is not None
        else float(geometry.chamber_id_m)
    )
    chamber_result = size_chamber_wall(governing_load_case, chamber_inner_diameter_m, materials["chamber_wall"], policy)
    forward_loaded_diameter_m = float(
        structural_config.get("forward_closure", {}).get("loaded_diameter_m")
        or float(geometry.injector_face_diameter_m) * float(structural_config["forward_closure"]["loaded_diameter_scale"])
    )
    aft_loaded_diameter_m = float(
        structural_config.get("aft_closure", {}).get("loaded_diameter_m")
        or float(geometry.chamber_id_m) * float(structural_config["aft_closure"]["loaded_diameter_scale"])
    )
    forward_closure_result = size_closure(
        closure_name="forward_closure",
        chamber_pressure_pa=governing_load_case.chamber_pressure_pa,
        ambient_pressure_pa=governing_load_case.ambient_pressure_pa,
        loaded_diameter_m=forward_loaded_diameter_m,
        material=materials["forward_closure"],
        policy=policy,
        model_type=policy.closure_model_type,
        minimum_thickness_m=structural_config["forward_closure"].get("minimum_thickness_m"),
        notes=["Forward closure span derived from injector-face support assumptions."],
    )
    aft_closure_result = size_closure(
        closure_name="aft_closure",
        chamber_pressure_pa=governing_load_case.chamber_pressure_pa,
        ambient_pressure_pa=governing_load_case.ambient_pressure_pa,
        loaded_diameter_m=aft_loaded_diameter_m,
        material=materials["aft_closure"],
        policy=policy,
        model_type=policy.closure_model_type,
        minimum_thickness_m=structural_config["aft_closure"].get("minimum_thickness_m"),
        notes=["Aft closure span derived from chamber-diameter support assumptions."],
    )
    injector_plate_result = size_injector_plate(
        structural_config,
        geometry,
        governing_load_case,
        materials["injector_plate"],
        policy,
        injector_geometry=injector_geometry,
    )
    fastener_result = size_fasteners(structural_config, governing_load_case, materials["fasteners"], policy)
    nozzle_mount_result = size_nozzle_mount(
        structural_config,
        geometry,
        governing_load_case,
        materials["nozzle_mount"],
        policy,
    )
    grain_support_result = evaluate_grain_support(
        structural_config,
        geometry,
        nominal_payload,
        ballistics_payload=ballistics_payload,
    )

    provisional_result = StructuralSizingResult(
        selected_materials={key: value.material_name for key, value in materials.items()},
        design_policy=policy,
        governing_load_case=governing_load_case,
        chamber_wall_result=chamber_result,
        forward_closure_result=forward_closure_result,
        aft_closure_result=aft_closure_result,
        injector_plate_result=injector_plate_result,
        fastener_result=fastener_result,
        nozzle_mount_result=nozzle_mount_result,
        grain_support_result=grain_support_result,
        mass_breakdown_kg={},
        total_structural_mass_estimate_kg=0.0,
        summary_margins={
            "chamber_wall": chamber_result.margin_to_allowable,
            "forward_closure": forward_closure_result.margin_to_allowable,
            "aft_closure": aft_closure_result.margin_to_allowable,
            "injector_plate": injector_plate_result.margin_to_allowable,
            "fasteners": fastener_result.margin_to_allowable,
            "nozzle_mount": nozzle_mount_result.margin_to_allowable,
        },
        validity_flags={},
        structural_valid=False,
        canonical_state={} if canonical_state is None else canonical_state.to_dict(),
        warnings=warnings,
        failure_reason=None,
        notes=[
            "First-pass structural sizing only.",
            "Detailed FEA, thermal derating, weld design, and certification logic are later refinements.",
        ],
    )
    mass_breakdown_kg = estimate_structural_mass_breakdown(
        geometry,
        injector_geometry,
        provisional_result,
        materials,
        structural_config,
    )
    result = StructuralSizingResult(
        selected_materials=provisional_result.selected_materials,
        design_policy=provisional_result.design_policy,
        governing_load_case=provisional_result.governing_load_case,
        chamber_wall_result=provisional_result.chamber_wall_result,
        forward_closure_result=provisional_result.forward_closure_result,
        aft_closure_result=provisional_result.aft_closure_result,
        injector_plate_result=provisional_result.injector_plate_result,
        fastener_result=provisional_result.fastener_result,
        nozzle_mount_result=provisional_result.nozzle_mount_result,
        grain_support_result=provisional_result.grain_support_result,
        mass_breakdown_kg=mass_breakdown_kg,
        total_structural_mass_estimate_kg=float(sum(mass_breakdown_kg.values())),
        summary_margins=provisional_result.summary_margins,
        validity_flags={},
        structural_valid=False,
        canonical_state=provisional_result.canonical_state,
        warnings=provisional_result.warnings,
        failure_reason=None,
        notes=provisional_result.notes,
    )
    validity_flags = build_validity_flags(result)
    failure_reasons: list[str] = []
    updated_canonical_state = canonical_state
    if updated_canonical_state is not None:
        shell_outer_diameter_m = 2.0 * (
            float(updated_canonical_state.geometry.shell_inner_radius_m) + float(chamber_result.selected_thickness_m)
        )
        geometry_valid_after_shell = updated_canonical_state.validity.geometry_valid
        if shell_outer_diameter_m > float(updated_canonical_state.constraints.max_shell_outer_diameter_m):
            geometry_valid_after_shell = False
            failure_reasons.append(
                f"Shell outer diameter {shell_outer_diameter_m:.3f} m exceeds maximum {updated_canonical_state.constraints.max_shell_outer_diameter_m:.3f} m."
            )
        updated_canonical_state = update_engine_state_validity(
            updated_canonical_state,
            geometry_valid=geometry_valid_after_shell,
            structural_valid=all(validity_flags.values()),
            injector_valid=updated_canonical_state.validity.injector_valid,
            shell_thickness_m=chamber_result.selected_thickness_m,
            failure_reasons=[*updated_canonical_state.diagnostics.failure_reasons, *failure_reasons],
        )
    final_result = StructuralSizingResult(
        selected_materials=result.selected_materials,
        design_policy=result.design_policy,
        governing_load_case=result.governing_load_case,
        chamber_wall_result=result.chamber_wall_result,
        forward_closure_result=result.forward_closure_result,
        aft_closure_result=result.aft_closure_result,
        injector_plate_result=result.injector_plate_result,
        fastener_result=result.fastener_result,
        nozzle_mount_result=result.nozzle_mount_result,
        grain_support_result=result.grain_support_result,
        mass_breakdown_kg=result.mass_breakdown_kg,
        total_structural_mass_estimate_kg=result.total_structural_mass_estimate_kg,
        summary_margins=result.summary_margins,
        validity_flags=validity_flags,
        structural_valid=all(validity_flags.values()),
        canonical_state={} if updated_canonical_state is None else updated_canonical_state.to_dict(),
        warnings=collect_structural_warnings(result),
        failure_reason=None if all(validity_flags.values()) else "One or more structural checks failed.",
        notes=result.notes,
    )
    destination = write_structural_outputs(output_dir, load_cases=load_cases, result=final_result)
    return {
        "output_dir": destination,
        "load_cases": load_cases,
        "result": final_result,
    }
