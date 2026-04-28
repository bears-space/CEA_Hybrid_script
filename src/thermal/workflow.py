"""High-level thermal sizing workflow orchestration."""

from __future__ import annotations

import math
from typing import Any, Mapping

from src.injector_design.injector_types import InjectorGeometryDefinition
from src.io_utils import deep_merge
from src.sizing.engine_state import EngineState, thermal_resistance_region_report, update_engine_state_validity
from src.sizing.geometry_types import GeometryDefinition
from src.structural.structural_types import StructuralSizingResult
from src.thermal.chamber_thermal import evaluate_cylindrical_region
from src.thermal.injector_face_thermal import evaluate_injector_face
from src.thermal.material_thermal_db import resolve_thermal_material_definition
from src.thermal.nozzle_thermal import evaluate_nozzle_region
from src.thermal.thermal_checks import build_validity_flags, collect_thermal_warnings
from src.thermal.thermal_export import write_thermal_outputs
from src.thermal.thermal_load_cases import build_thermal_load_cases
from src.thermal.thermal_mass import estimate_thermal_protection_mass_kg
from src.thermal.thermal_types import ThermalDesignPolicy, ThermalSizingResult
from src.thermal.throat_insert_sizing import size_protection_layer


def _canonical_region_reports(
    *,
    canonical_state: EngineState,
    thermal_config: Mapping[str, Any],
    result: ThermalSizingResult,
) -> tuple[list[dict[str, Any]], bool, list[str]]:
    reports: list[dict[str, Any]] = []
    failure_reasons: list[str] = []
    policy = canonical_state.constraints
    thermal_policy = _design_policy(thermal_config)
    shell_material = resolve_thermal_material_definition(
        canonical_state.materials.shell_material,
        thermal_config,
        thermal_policy,
    )
    liner_material = resolve_thermal_material_definition(
        canonical_state.materials.liner_material,
        thermal_config,
        thermal_policy,
    )
    region_inputs = [
        ("prechamber", result.prechamber_result.region if result.prechamber_result is not None else None, canonical_state.geometry.prechamber_length_m, float(thermal_config["region_gas_temp_scale"]["prechamber"])),
        ("chamber", result.chamber_region_result.region, canonical_state.geometry.grain_length_m, float(thermal_config["region_gas_temp_scale"]["chamber"])),
        ("postchamber", result.postchamber_result.region if result.postchamber_result is not None else None, canonical_state.geometry.postchamber_length_m, float(thermal_config["region_gas_temp_scale"]["postchamber"])),
    ]
    for region_name, region_result, length_m, gas_temp_scale in region_inputs:
        if region_result is None or length_m <= 0.0:
            continue
        report = thermal_resistance_region_report(
            region=region_name,
            time_s=list(region_result.time_history_s),
            gas_temperature_k_time=[float(value) * gas_temp_scale for value in result.governing_load_case.chamber_temp_k_time],
            gas_side_htc_w_m2k_time=list(region_result.gas_side_htc_history_w_m2k),
            hot_gas_radius_m=canonical_state.geometry.hot_gas_radius_m,
            liner_thickness_m=canonical_state.geometry.liner_thickness_m,
            shell_thickness_m=canonical_state.geometry.shell_thickness_m,
            length_m=length_m,
            liner_conductivity_w_mk=liner_material.conductivity_w_mk,
            shell_conductivity_w_mk=shell_material.conductivity_w_mk,
            outer_h_w_m2k=thermal_policy.outer_h_guess_w_m2k,
            ambient_temp_k=thermal_policy.outer_ambient_temp_k,
            use_ablative_liner_model=policy.use_ablative_liner_model,
            rho_liner=policy.rho_liner,
            H_ablation_effective=policy.H_ablation_effective,
            T_pyrolysis_k=policy.T_pyrolysis_k,
        )
        if report["peak_shell_inner_wall_temp_k"] > policy.maximum_shell_inner_wall_temp_k:
            failure_reasons.append(
                f"{region_name} shell inner wall temperature {report['peak_shell_inner_wall_temp_k']:.1f} K exceeds maximum {policy.maximum_shell_inner_wall_temp_k:.1f} K."
            )
        if report["remaining_liner_thickness_m"] < policy.minimum_remaining_liner_thickness_m:
            failure_reasons.append(
                f"{region_name} remaining liner thickness {report['remaining_liner_thickness_m']:.4f} m is below minimum {policy.minimum_remaining_liner_thickness_m:.4f} m."
            )
        reports.append(report)
    return reports, not failure_reasons, failure_reasons


def merge_thermal_config(
    study_config: Mapping[str, Any],
    override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the thermal config section after applying optional overrides."""

    override_section = dict(override or {})
    if "thermal" in override_section and isinstance(override_section["thermal"], Mapping):
        override_section = dict(override_section["thermal"])
    return deep_merge(dict(study_config.get("thermal", {})), override_section)


def _design_policy(thermal_config: Mapping[str, Any]) -> ThermalDesignPolicy:
    policy = dict(thermal_config.get("design_policy", {}))
    return ThermalDesignPolicy(
        gas_side_htc_model=str(policy["gas_side_htc_model"]),
        throat_htc_multiplier=float(policy["throat_htc_multiplier"]),
        injector_face_htc_multiplier=float(policy["injector_face_htc_multiplier"]),
        use_lumped_wall_model=bool(policy["use_lumped_wall_model"]),
        wall_model_type=str(policy["wall_model_type"]),
        inner_wall_node_count=int(policy["inner_wall_node_count"]),
        outer_convection_model=str(policy["outer_convection_model"]),
        outer_h_guess_w_m2k=float(policy["outer_h_guess_w_m2k"]),
        outer_ambient_temp_k=float(policy["outer_ambient_temp_k"]),
        radiation_enabled=bool(policy["radiation_enabled"]),
        surface_emissivity=float(policy["surface_emissivity"]),
        service_temp_margin_k=float(policy["service_temp_margin_k"]),
        sacrificial_liner_allowed=bool(policy["sacrificial_liner_allowed"]),
        sacrificial_throat_insert_allowed=bool(policy["sacrificial_throat_insert_allowed"]),
        temperature_limit_basis=str(policy["temperature_limit_basis"]),
        thermal_roundup_increment_m=float(policy["thermal_roundup_increment_m"]),
        minimum_protection_thickness_m=float(policy["minimum_protection_thickness_m"]),
    )


def _protection_surface_area_m2(inner_diameter_m: float, length_m: float) -> float:
    return math.pi * float(inner_diameter_m) * float(length_m)


def _evaluate_candidate(
    *,
    thermal_config: Mapping[str, Any],
    policy: ThermalDesignPolicy,
    materials: Mapping[str, Any],
    geometry: GeometryDefinition,
    structural_result: StructuralSizingResult,
    load_case: Any,
    injector_geometry: InjectorGeometryDefinition | None,
) -> ThermalSizingResult:
    chamber_wall_thickness_m = float(
        thermal_config.get("chamber", {}).get("selected_wall_thickness_m")
        or structural_result.chamber_wall_result.selected_thickness_m
    )
    throat_wall_thickness_m = float(
        thermal_config.get("throat", {}).get("selected_wall_thickness_m")
        or chamber_wall_thickness_m
    )
    diverging_wall_thickness_m = float(
        thermal_config.get("diverging_nozzle", {}).get("selected_wall_thickness_m")
        or chamber_wall_thickness_m
    )
    injector_plate_thickness_m = float(
        thermal_config.get("injector_face", {}).get("selected_thickness_m")
        or structural_result.injector_plate_result.selected_thickness_m
        or geometry.injector_plate_thickness_m
    )

    chamber_region_result = evaluate_cylindrical_region(
        region_name="chamber",
        region_length_m=float(geometry.grain_length_m),
        inner_diameter_m=float(geometry.chamber_id_m),
        wall_thickness_m=chamber_wall_thickness_m,
        load_case=load_case,
        material=materials["chamber_wall"],
        policy=policy,
        gas_temperature_scale=float(thermal_config["region_gas_temp_scale"]["chamber"]),
    )
    prechamber_result = None
    if float(geometry.prechamber_length_m) > 0.0:
        prechamber_result = evaluate_cylindrical_region(
            region_name="prechamber",
            region_length_m=float(geometry.prechamber_length_m),
            inner_diameter_m=float(geometry.chamber_id_m),
            wall_thickness_m=chamber_wall_thickness_m,
            load_case=load_case,
            material=materials["prechamber"],
            policy=policy,
            gas_temperature_scale=float(thermal_config["region_gas_temp_scale"]["prechamber"]),
        )
    postchamber_result = None
    if float(geometry.postchamber_length_m) > 0.0:
        postchamber_result = evaluate_cylindrical_region(
            region_name="postchamber",
            region_length_m=float(geometry.postchamber_length_m),
            inner_diameter_m=float(geometry.chamber_id_m),
            wall_thickness_m=chamber_wall_thickness_m,
            load_case=load_case,
            material=materials["postchamber"],
            policy=policy,
            gas_temperature_scale=float(thermal_config["region_gas_temp_scale"]["postchamber"]),
        )

    converging_half_angle_deg = float(thermal_config["nozzle_geometry"]["converging_half_angle_deg"])
    diverging_half_angle_deg = float(thermal_config["nozzle_geometry"]["diverging_half_angle_deg"])
    converging_length_m = float(geometry.converging_section_arc_length_m or geometry.converging_section_length_m or 0.0)
    if converging_length_m <= 0.0:
        converging_length_m = max(
            (float(geometry.chamber_id_m) - float(geometry.throat_diameter_m))
            / (2.0 * math.tan(math.radians(max(converging_half_angle_deg, 1.0)))),
            float(geometry.throat_diameter_m),
        )
    diverging_length_m = float(geometry.nozzle_arc_length_m or geometry.nozzle_length_m or 0.0)
    if diverging_length_m <= 0.0:
        diverging_length_m = max(
            (float(geometry.nozzle_exit_diameter_m) - float(geometry.throat_diameter_m))
            / (2.0 * math.tan(math.radians(max(diverging_half_angle_deg, 1.0)))),
            float(geometry.throat_diameter_m),
        )
    throat_axial_length_m = max(
        float(thermal_config["throat"]["axial_length_scale"]) * float(geometry.throat_diameter_m),
        float(geometry.throat_diameter_m) * 0.5,
    )
    throat_result = evaluate_nozzle_region(
        region_name="throat",
        characteristic_diameter_m=float(geometry.throat_diameter_m),
        axial_length_m=throat_axial_length_m + 0.5 * converging_length_m,
        wall_thickness_m=throat_wall_thickness_m,
        load_case=load_case,
        material=materials["throat"],
        policy=policy,
        area_ratio=1.0,
    )
    diverging_nozzle_result = evaluate_nozzle_region(
        region_name="diverging_nozzle",
        characteristic_diameter_m=float(geometry.nozzle_exit_diameter_m),
        axial_length_m=diverging_length_m,
        wall_thickness_m=diverging_wall_thickness_m,
        load_case=load_case,
        material=materials["diverging_nozzle"],
        policy=policy,
        area_ratio=float(geometry.nozzle_area_ratio),
    )
    injector_face_result = evaluate_injector_face(
        active_face_diameter_m=float(
            injector_geometry.active_face_diameter_m if injector_geometry is not None else geometry.injector_face_diameter_m
        ),
        plate_thickness_m=injector_plate_thickness_m,
        load_case=load_case,
        material=materials["injector_face"],
        policy=policy,
        injector_geometry=injector_geometry,
        structural_plate_thickness_m=structural_result.injector_plate_result.selected_thickness_m,
    )

    liner_result = None
    liner_settings = dict(thermal_config.get("liner", {}))
    if bool(liner_settings.get("enabled")) and policy.sacrificial_liner_allowed:
        chamber_total_length_m = float(geometry.grain_length_m + geometry.prechamber_length_m + geometry.postchamber_length_m)
        liner_result = size_protection_layer(
            protection_name="liner",
            protected_region="chamber",
            surface_area_m2=_protection_surface_area_m2(float(geometry.chamber_id_m), chamber_total_length_m),
            characteristic_diameter_m=float(geometry.chamber_id_m),
            base_wall_thickness_m=chamber_wall_thickness_m,
            base_material=materials["chamber_wall"],
            protection_material=materials["liner"],
            load_case=load_case,
            policy=policy,
            selected_initial_thickness_m=float(liner_settings.get("selected_thickness_m", 0.0) or 0.0),
            throat_multiplier=policy.throat_htc_multiplier,
            injector_face_multiplier=policy.injector_face_htc_multiplier,
            area_ratio=1.0,
        )

    throat_insert_result = None
    insert_settings = dict(thermal_config.get("throat_insert", {}))
    if bool(insert_settings.get("enabled")) and policy.sacrificial_throat_insert_allowed:
        throat_insert_result = size_protection_layer(
            protection_name="throat_insert",
            protected_region="throat",
            surface_area_m2=_protection_surface_area_m2(float(geometry.throat_diameter_m), throat_axial_length_m),
            characteristic_diameter_m=float(geometry.throat_diameter_m),
            base_wall_thickness_m=throat_wall_thickness_m,
            base_material=materials["throat"],
            protection_material=materials["throat_insert"],
            load_case=load_case,
            policy=policy,
            selected_initial_thickness_m=float(insert_settings.get("selected_thickness_m", 0.0) or 0.0),
            throat_multiplier=policy.throat_htc_multiplier,
            injector_face_multiplier=policy.injector_face_htc_multiplier,
            area_ratio=1.0,
        )

    selected_materials = {key: value.material_name for key, value in materials.items()}
    total_protection_mass_kg = estimate_thermal_protection_mass_kg(liner_result, throat_insert_result)
    summary_margins = {
        "chamber": chamber_region_result.region.thermal_margin_k,
        "prechamber": prechamber_result.region.thermal_margin_k if prechamber_result is not None else chamber_region_result.region.thermal_margin_k,
        "postchamber": postchamber_result.region.thermal_margin_k if postchamber_result is not None else chamber_region_result.region.thermal_margin_k,
        "throat": throat_result.region.thermal_margin_k,
        "diverging_nozzle": diverging_nozzle_result.region.thermal_margin_k,
        "injector_face": injector_face_result.region.thermal_margin_k,
    }
    if liner_result is not None:
        summary_margins["liner"] = liner_result.thermal_margin_k
    if throat_insert_result is not None:
        summary_margins["throat_insert"] = throat_insert_result.thermal_margin_k

    preliminary = ThermalSizingResult(
        governing_load_case=load_case,
        chamber_region_result=chamber_region_result,
        prechamber_result=prechamber_result,
        postchamber_result=postchamber_result,
        throat_result=throat_result,
        diverging_nozzle_result=diverging_nozzle_result,
        injector_face_result=injector_face_result,
        optional_liner_result=liner_result,
        optional_throat_insert_result=throat_insert_result,
        selected_materials=selected_materials,
        design_policy=policy,
        case_summaries=[],
        total_thermal_protection_mass_estimate_kg=total_protection_mass_kg,
        summary_margins=summary_margins,
        validity_flags={},
        thermal_valid=False,
        canonical_state={},
        canonical_region_reports=[],
        warnings=[],
        failure_reason=None,
        notes=[
            "First-pass thermal sizing only.",
            "Detailed CFD, conjugate heat transfer, ablation, cooling design, and hot-fire calibration are later refinements.",
        ],
    )
    validity_flags = build_validity_flags(preliminary)
    thermal_valid = all(validity_flags.values())
    return ThermalSizingResult(
        governing_load_case=preliminary.governing_load_case,
        chamber_region_result=preliminary.chamber_region_result,
        prechamber_result=preliminary.prechamber_result,
        postchamber_result=preliminary.postchamber_result,
        throat_result=preliminary.throat_result,
        diverging_nozzle_result=preliminary.diverging_nozzle_result,
        injector_face_result=preliminary.injector_face_result,
        optional_liner_result=preliminary.optional_liner_result,
        optional_throat_insert_result=preliminary.optional_throat_insert_result,
        selected_materials=preliminary.selected_materials,
        design_policy=preliminary.design_policy,
        case_summaries=[],
        total_thermal_protection_mass_estimate_kg=preliminary.total_thermal_protection_mass_estimate_kg,
        summary_margins=preliminary.summary_margins,
        validity_flags=validity_flags,
        thermal_valid=thermal_valid,
        canonical_state={},
        canonical_region_reports=[],
        warnings=collect_thermal_warnings(preliminary),
        failure_reason=None if thermal_valid else "One or more thermal checks failed.",
        notes=preliminary.notes,
    )


def run_thermal_sizing_workflow(
    study_config: Mapping[str, Any],
    thermal_config: Mapping[str, Any],
    output_dir: str,
    *,
    geometry: GeometryDefinition,
    structural_result: StructuralSizingResult,
    nominal_payload: Mapping[str, Any],
    injector_geometry: InjectorGeometryDefinition | None = None,
    corner_payload: Mapping[str, Any] | None = None,
    ballistics_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run first-pass thermal sizing and export the standard output bundle."""

    canonical_state = EngineState.from_mapping(geometry.engine_state) if geometry.engine_state else None
    policy = _design_policy(thermal_config)
    materials = {
        component: resolve_thermal_material_definition(material_name, thermal_config, policy)
        for component, material_name in dict(thermal_config.get("component_materials", {})).items()
    }
    load_cases, warnings = build_thermal_load_cases(
        thermal_config,
        geometry,
        nominal_payload=nominal_payload,
        corner_payload=corner_payload,
        ballistics_payload=ballistics_payload,
    )
    candidates = [
        _evaluate_candidate(
            thermal_config=thermal_config,
            policy=policy,
            materials=materials,
            geometry=geometry,
            structural_result=structural_result,
            load_case=load_case,
            injector_geometry=injector_geometry,
        )
        for load_case in load_cases
    ]
    candidate_summaries = [
        {
            "case_name": candidate.governing_load_case.case_name,
            "source_stage": candidate.governing_load_case.source_stage,
            "minimum_margin_k": min(candidate.summary_margins.values()),
            "governing_region": min(candidate.summary_margins, key=candidate.summary_margins.get),
            "peak_throat_temp_k": candidate.throat_result.region.peak_inner_wall_temp_k,
            "peak_chamber_temp_k": candidate.chamber_region_result.region.peak_inner_wall_temp_k,
        }
        for candidate in candidates
    ]
    final_result = min(candidates, key=lambda candidate: min(candidate.summary_margins.values()))
    final_result = ThermalSizingResult(
        governing_load_case=final_result.governing_load_case,
        chamber_region_result=final_result.chamber_region_result,
        prechamber_result=final_result.prechamber_result,
        postchamber_result=final_result.postchamber_result,
        throat_result=final_result.throat_result,
        diverging_nozzle_result=final_result.diverging_nozzle_result,
        injector_face_result=final_result.injector_face_result,
        optional_liner_result=final_result.optional_liner_result,
        optional_throat_insert_result=final_result.optional_throat_insert_result,
        selected_materials=final_result.selected_materials,
        design_policy=final_result.design_policy,
        case_summaries=candidate_summaries,
        total_thermal_protection_mass_estimate_kg=final_result.total_thermal_protection_mass_estimate_kg,
        summary_margins=final_result.summary_margins,
        validity_flags=final_result.validity_flags,
        thermal_valid=final_result.thermal_valid,
        canonical_state={},
        canonical_region_reports=[],
        warnings=[*warnings, *final_result.warnings],
        failure_reason=final_result.failure_reason,
        notes=final_result.notes,
    )
    if canonical_state is not None:
        region_reports, canonical_thermal_valid, canonical_failures = _canonical_region_reports(
            canonical_state=canonical_state,
            thermal_config=thermal_config,
            result=final_result,
        )
        updated_state = update_engine_state_validity(
            canonical_state,
            structural_valid=canonical_state.validity.structural_valid,
            thermal_valid=bool(final_result.thermal_valid and canonical_thermal_valid),
            failure_reasons=[*canonical_state.diagnostics.failure_reasons, *canonical_failures],
            warnings=[*warnings, *final_result.warnings],
            thermal_updates={"region_reports": region_reports},
        )
        final_result = ThermalSizingResult(
            governing_load_case=final_result.governing_load_case,
            chamber_region_result=final_result.chamber_region_result,
            prechamber_result=final_result.prechamber_result,
            postchamber_result=final_result.postchamber_result,
            throat_result=final_result.throat_result,
            diverging_nozzle_result=final_result.diverging_nozzle_result,
            injector_face_result=final_result.injector_face_result,
            optional_liner_result=final_result.optional_liner_result,
            optional_throat_insert_result=final_result.optional_throat_insert_result,
            selected_materials=final_result.selected_materials,
            design_policy=final_result.design_policy,
            case_summaries=final_result.case_summaries,
            total_thermal_protection_mass_estimate_kg=final_result.total_thermal_protection_mass_estimate_kg,
            summary_margins=final_result.summary_margins,
            validity_flags=final_result.validity_flags,
            thermal_valid=bool(final_result.thermal_valid and canonical_thermal_valid),
            canonical_state=updated_state.to_dict(),
            canonical_region_reports=region_reports,
            warnings=[*warnings, *final_result.warnings],
            failure_reason=(
                None
                if final_result.thermal_valid and canonical_thermal_valid
                else "One or more thermal checks failed."
            ),
            notes=final_result.notes,
        )
    destination = write_thermal_outputs(output_dir, load_cases=load_cases, result=final_result)
    return {
        "output_dir": destination,
        "load_cases": load_cases,
        "result": final_result,
    }
