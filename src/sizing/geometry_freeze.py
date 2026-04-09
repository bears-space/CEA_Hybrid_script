"""Step 2 geometry freeze built on top of the reusable Step 1 workflow outputs."""

from __future__ import annotations

from dataclasses import replace
import math
from typing import Any, Mapping

from src.analysis.constraints import evaluate_constraints
from src.analysis.metrics import extract_case_metrics
from src.cea.cea_interface import get_cea_performance_point
from src.cea.cea_types import CEAPerformancePoint, CEASweepResult
from src.config_schema import build_design_config
from src.sizing.geometry_rules import (
    area_from_diameter,
    cylinder_volume_from_diameter,
    cylindrical_port_volume,
    diameter_from_area,
    evaluate_geometry_checks,
)
from src.sizing.geometry_types import GeometryDefinition


def _normalize_nominal_payload(config: Mapping[str, Any], nominal_result: Mapping[str, Any]) -> dict[str, Any]:
    if "result" in nominal_result and "metrics" in nominal_result:
        payload = dict(nominal_result)
        payload.setdefault("constraints", evaluate_constraints(payload["metrics"], config.get("constraints", {})))
        return payload

    result = dict(nominal_result)
    metrics = extract_case_metrics(result, config)
    constraints = evaluate_constraints(metrics, config.get("constraints", {}))
    return {
        "result": result,
        "metrics": metrics,
        "constraints": constraints,
    }


def _cea_reference_dict(cea_result: CEAPerformancePoint | CEASweepResult | list[CEAPerformancePoint] | None) -> dict[str, Any] | None:
    if cea_result is None:
        return None
    point = cea_result
    if isinstance(cea_result, (CEASweepResult, list)):
        point = get_cea_performance_point(cea_result)
    assert isinstance(point, CEAPerformancePoint)
    return {
        "pc_bar": point.case_input.pc_bar,
        "of_ratio": point.case_input.of_ratio,
        "ae_at": point.case_input.ae_at,
        "cstar_mps": point.cstar_mps,
        "isp_s": point.isp_s,
        "cf": point.cf,
        "gamma_e": point.gamma_e,
        "molecular_weight_exit": point.molecular_weight_exit,
        "chamber_temperature_k": point.chamber_temperature_k,
        "exit_temperature_k": point.exit_temperature_k,
        "exit_pressure_bar": point.exit_pressure_bar,
    }


def _top_sensitivity_note(sensitivity_summary: Mapping[str, Any] | None, metric_order: list[str]) -> tuple[str | None, str | None, list[str]]:
    if not sensitivity_summary:
        return None, None, []
    notes: list[str] = []
    primary_metric = metric_order[0] if metric_order else None
    primary_parameter = None
    rankings = sensitivity_summary.get("rankings", {})

    for metric in metric_order:
        rows = rankings.get(metric) or []
        if not rows:
            continue
        top = rows[0]
        if primary_metric is None:
            primary_metric = metric
        if primary_parameter is None:
            primary_parameter = top.get("parameter")
        value = top.get("normalized_sensitivity_abs")
        value_text = "n/a" if value is None else f"{float(value):.3f}"
        if value is not None and not math.isfinite(float(value)):
            value_text = "non-finite"
        notes.append(f"Top OAT driver for {metric}: {top.get('parameter')} ({value_text} abs normalized sensitivity).")
    return primary_metric, primary_parameter, notes


def _corner_case_summary(corner_summary: Mapping[str, Any] | None) -> tuple[bool | None, list[str]]:
    if not corner_summary:
        return None, []
    rows = corner_summary.get("corners", [])
    if not rows:
        return None, []

    all_pass = all(bool(item.get("constraints", {}).get("all_pass")) for item in rows)
    max_pc = max(float(item["metrics"]["pc_peak_bar"]) for item in rows)
    max_thrust = max(float(item["metrics"]["thrust_peak_n"]) for item in rows)
    notes = [
        f"Corner-case compatibility: {'all pass' if all_pass else 'at least one failure'}; max pc_peak={max_pc:.2f} bar, max thrust_peak={max_thrust:.2f} N."
    ]
    if not all_pass:
        failed = [item["case_name"] for item in rows if not item.get("constraints", {}).get("all_pass")]
        notes.append(f"Failed corner cases: {', '.join(failed)}.")
    return all_pass, notes


def freeze_first_pass_geometry(
    config: Mapping[str, Any],
    cea_result: CEAPerformancePoint | CEASweepResult | list[CEAPerformancePoint] | None,
    nominal_result: Mapping[str, Any],
    sensitivity_summary: Mapping[str, Any] | None = None,
    corner_summary: Mapping[str, Any] | None = None,
) -> GeometryDefinition:
    """Freeze a buildable Step 2 baseline geometry from the current design state."""

    study_config = build_design_config(config)
    nominal_payload = _normalize_nominal_payload(study_config, nominal_result)
    runtime = nominal_payload["result"].get("runtime")
    if runtime is None:
        raise ValueError("Nominal result does not include runtime sizing outputs; cannot freeze geometry.")

    derived = runtime["derived"]
    policy = study_config["geometry_policy"]
    metrics = nominal_payload["metrics"]
    constraints = nominal_payload["constraints"]

    grain_length_m = float(derived["grain_length_m"])
    port_radius_initial_m = float(derived["initial_port_radius_mm"]) * 1.0e-3
    grain_outer_radius_raw_mm = derived.get("grain_outer_radius_mm")
    if grain_outer_radius_raw_mm is None:
        raise ValueError("Nominal result did not provide a grain outer radius.")
    grain_outer_radius_m = float(grain_outer_radius_raw_mm) * 1.0e-3
    port_count = int(derived.get("port_count", study_config["nominal"]["blowdown"]["grain"]["port_count"]))
    radial_web_initial_m = grain_outer_radius_m - port_radius_initial_m

    chamber_id_m = 2.0 * (grain_outer_radius_m + float(policy["grain_to_chamber_radial_clearance_m"]))
    injector_face_diameter_m = chamber_id_m * float(policy["injector_face_margin_factor"])
    prechamber_enabled = bool(policy["prechamber_enabled"])
    postchamber_enabled = bool(policy["postchamber_enabled"])
    prechamber_length_m = grain_length_m * float(policy["prechamber_length_fraction_of_grain"]) if prechamber_enabled else 0.0
    postchamber_length_m = grain_length_m * float(policy["postchamber_length_fraction_of_grain"]) if postchamber_enabled else 0.0

    throat_area_m2 = float(derived["nozzle_throat_area_mm2"]) * 1.0e-6
    nozzle_exit_area_m2 = float(derived["nozzle_exit_area_mm2"]) * 1.0e-6
    throat_diameter_m = diameter_from_area(throat_area_m2)
    nozzle_exit_diameter_m = diameter_from_area(nozzle_exit_area_m2)
    nozzle_area_ratio = nozzle_exit_area_m2 / throat_area_m2

    chamber_cross_section_area_m2 = area_from_diameter(chamber_id_m)
    injector_face_area_m2 = area_from_diameter(injector_face_diameter_m)
    free_volume_initial_m3 = (
        cylinder_volume_from_diameter(prechamber_length_m, chamber_id_m)
        + cylindrical_port_volume(grain_length_m, port_radius_initial_m, port_count)
        + cylinder_volume_from_diameter(postchamber_length_m, chamber_id_m)
    )
    total_chamber_length_m = (
        float(policy["injector_plate_thickness_m"]) + prechamber_length_m + grain_length_m + postchamber_length_m
    )
    lstar_initial_m = free_volume_initial_m3 / throat_area_m2

    sensitivity_metric, sensitivity_parameter, sensitivity_notes = _top_sensitivity_note(
        sensitivity_summary,
        list(study_config.get("sensitivity_metrics", [])),
    )
    corner_cases_all_pass, corner_notes = _corner_case_summary(corner_summary)

    notes = [
        "Frozen from the Step 1 nominal 0D runtime sizing outputs without changing the underlying blowdown physics.",
        f"Injector architecture placeholder remains an axial showerhead with equivalent CdA={float(derived['injector_total_area_mm2']) * 1.0e-6:.6e} m^2.",
    ]
    notes.extend(sensitivity_notes)
    notes.extend(corner_notes)

    cea_reference = _cea_reference_dict(cea_result)
    if cea_reference is not None:
        notes.append(
            f"CEA reference point: Pc={cea_reference['pc_bar']:.2f} bar, O/F={cea_reference['of_ratio']:.3f}, c*={cea_reference['cstar_mps']:.1f} m/s."
        )

    geometry = GeometryDefinition(
        chamber_id_m=chamber_id_m,
        injector_face_diameter_m=injector_face_diameter_m,
        prechamber_length_m=prechamber_length_m,
        grain_length_m=grain_length_m,
        port_radius_initial_m=port_radius_initial_m,
        grain_outer_radius_m=grain_outer_radius_m,
        postchamber_length_m=postchamber_length_m,
        throat_diameter_m=throat_diameter_m,
        nozzle_exit_diameter_m=nozzle_exit_diameter_m,
        nozzle_area_ratio=nozzle_area_ratio,
        injector_plate_thickness_m=float(policy["injector_plate_thickness_m"]),
        chamber_wall_thickness_guess_m=float(policy["chamber_wall_thickness_guess_m"]),
        total_chamber_length_m=total_chamber_length_m,
        free_volume_initial_m3=free_volume_initial_m3,
        lstar_initial_m=lstar_initial_m,
        single_port_baseline=bool(policy["single_port_baseline"]),
        prechamber_enabled=prechamber_enabled,
        postchamber_enabled=postchamber_enabled,
        axial_showerhead_injector_baseline=bool(policy["axial_showerhead_injector_baseline"]),
        injector_discharges_to_prechamber=bool(policy["injector_discharges_to_prechamber"]),
        port_count=port_count,
        radial_web_initial_m=radial_web_initial_m,
        chamber_cross_section_area_m2=chamber_cross_section_area_m2,
        injector_face_area_m2=injector_face_area_m2,
        throat_area_m2=throat_area_m2,
        nozzle_exit_area_m2=nozzle_exit_area_m2,
        injector_equivalent_area_m2=float(derived["injector_total_area_mm2"]) * 1.0e-6,
        nominal_pc_bar=float(metrics["pc_avg_bar"]) if metrics.get("pc_avg_bar") is not None else None,
        nominal_thrust_avg_n=float(metrics["thrust_avg_n"]) if metrics.get("thrust_avg_n") is not None else None,
        nominal_constraint_pass=bool(constraints.get("all_pass")),
        corner_cases_all_pass=corner_cases_all_pass,
        sensitivity_driver_metric=sensitivity_metric,
        sensitivity_top_parameter=sensitivity_parameter,
        cea_reference=cea_reference,
        source_summary={
            "grain_length_source": derived.get("grain_length_source"),
            "initial_port_source": derived.get("initial_port_source"),
            "outer_radius_source": derived.get("outer_radius_source"),
            "injector_total_area_source": derived.get("injector_total_area_source"),
            "target_pc_bar": derived.get("target_pc_bar"),
            "target_initial_gox_kg_m2_s": derived.get("target_initial_gox_kg_m2_s"),
            "tank_initial_pressure_bar": derived.get("tank_initial_pressure_bar"),
        },
        notes=notes,
    )

    checks, geometry_valid, warnings = evaluate_geometry_checks(geometry, policy)
    return replace(geometry, checks=checks, geometry_valid=geometry_valid, warnings=warnings)
