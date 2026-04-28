"""Baseline geometry freeze built on top of the reusable design-workflow outputs."""

from __future__ import annotations

from dataclasses import replace
import math
from typing import Any, Mapping

from src.analysis.constraints import evaluate_constraints
from src.analysis.metrics import extract_case_metrics
from src.cea.cea_interface import get_cea_performance_point
from src.cea.cea_types import CEAPerformancePoint, CEASweepResult
from src.config import build_design_config
from src.sizing.engine_state import build_canonical_engine_state
from src.sizing.geometry_rules import area_from_diameter
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
    """Freeze a buildable baseline geometry from the current design state."""

    study_config = build_design_config(config)
    nominal_payload = _normalize_nominal_payload(study_config, nominal_result)
    runtime = nominal_payload["result"].get("runtime")
    if runtime is None:
        raise ValueError("Nominal result does not include runtime sizing outputs; cannot freeze geometry.")

    derived = runtime["derived"]
    policy = study_config["geometry_policy"]
    metrics = nominal_payload["metrics"]
    constraints = nominal_payload["constraints"]
    state = build_canonical_engine_state(study_config, nominal_payload)
    geometry_state = state.geometry

    chamber_id_m = 2.0 * geometry_state.hot_gas_radius_m
    throat_area_m2 = math.pi * geometry_state.throat_radius_m**2
    nozzle_exit_area_m2 = math.pi * geometry_state.exit_radius_m**2
    throat_diameter_m = 2.0 * geometry_state.throat_radius_m
    nozzle_exit_diameter_m = 2.0 * geometry_state.exit_radius_m
    nozzle_area_ratio = geometry_state.area_expansion_ratio
    grain_length_m = geometry_state.grain_length_m
    port_radius_initial_m = geometry_state.grain_port_radius_initial_m
    grain_outer_radius_m = geometry_state.grain_outer_radius_m
    port_count = int(derived.get("port_count", study_config["nominal"]["blowdown"]["grain"]["port_count"]))
    radial_web_initial_m = geometry_state.initial_web_thickness_m
    injector_face_diameter_m = chamber_id_m * float(policy["injector_face_margin_factor"])
    prechamber_enabled = bool(policy["prechamber_enabled"])
    postchamber_enabled = bool(policy["postchamber_enabled"])
    prechamber_length_m = geometry_state.prechamber_length_m
    postchamber_length_m = geometry_state.postchamber_length_m
    chamber_wall_thickness_guess_m = geometry_state.shell_thickness_m
    chamber_inner_diameter_including_liner_m = chamber_id_m
    chamber_inner_diameter_excluding_liner_m = 2.0 * geometry_state.shell_inner_radius_m
    chamber_outer_diameter_excluding_liner_m = 2.0 * geometry_state.shell_outer_radius_m
    chamber_outer_diameter_including_liner_m = chamber_outer_diameter_excluding_liner_m
    inner_liner_thickness_m = geometry_state.liner_thickness_m
    fuel_inner_diameter_m = 2.0 * geometry_state.grain_port_radius_initial_m
    fuel_outer_diameter_m = 2.0 * geometry_state.grain_outer_radius_m
    chamber_cross_section_area_m2 = area_from_diameter(chamber_id_m)
    injector_face_area_m2 = area_from_diameter(injector_face_diameter_m)
    free_volume_initial_m3 = geometry_state.hot_gas_free_volume_initial_m3
    total_chamber_length_m = geometry_state.chamber_total_length_m
    lstar_initial_m = geometry_state.lstar_initial_m

    sensitivity_metric, sensitivity_parameter, sensitivity_notes = _top_sensitivity_note(
        sensitivity_summary,
        list(study_config.get("sensitivity_metrics", [])),
    )
    corner_cases_all_pass, corner_notes = _corner_case_summary(corner_summary)

    notes = [
        "Frozen from the nominal 0D runtime sizing outputs without changing the underlying blowdown physics.",
        "Canonical geometry generated with the diameter-first sizing policy before any chamber-length growth was allowed.",
        (
            "Injector architecture is sized from oxidizer flow using a fixed hole diameter and an integer hole count "
            f"that closes the required total oxidizer-hole area at {geometry_state.injector_total_hole_area_m2:.6e} m^2."
        ),
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
        chamber_inner_diameter_including_liner_m=chamber_inner_diameter_including_liner_m,
        chamber_outer_diameter_including_liner_m=chamber_outer_diameter_including_liner_m,
        chamber_inner_diameter_excluding_liner_m=chamber_inner_diameter_excluding_liner_m,
        chamber_outer_diameter_excluding_liner_m=chamber_outer_diameter_excluding_liner_m,
        fuel_inner_diameter_m=fuel_inner_diameter_m,
        fuel_outer_diameter_m=fuel_outer_diameter_m,
        inner_liner_thickness_m=inner_liner_thickness_m,
        injector_hole_count=geometry_state.injector_hole_count,
        injector_total_hole_area_m2=geometry_state.injector_total_hole_area_m2,
        injector_hole_diameter_m=geometry_state.injector_hole_diameter_m,
        converging_throat_half_angle_deg=geometry_state.converging_half_angle_deg,
        diverging_throat_half_angle_deg=geometry_state.diverging_half_angle_deg,
        throat_blend_radius_m=geometry_state.throat_blend_radius_m,
        converging_section_length_m=geometry_state.nozzle_converging_length_m,
        converging_section_arc_length_m=geometry_state.nozzle_converging_length_m,
        converging_straight_length_m=geometry_state.nozzle_converging_length_m,
        converging_blend_arc_length_m=0.0,
        nozzle_length_m=geometry_state.nozzle_diverging_length_m,
        nozzle_arc_length_m=geometry_state.nozzle_diverging_length_m,
        nozzle_straight_length_m=geometry_state.nozzle_diverging_length_m,
        nozzle_blend_arc_length_m=0.0,
        nozzle_contour_style="conical_blended",
        nozzle_profile={
            "converging_half_angle_deg": geometry_state.converging_half_angle_deg,
            "diverging_half_angle_deg": geometry_state.diverging_half_angle_deg,
            "throat_blend_radius_m": geometry_state.throat_blend_radius_m,
            "throat_blend_radius_factor": float(study_config["thermal"]["nozzle_geometry"]["throat_blend_radius_factor"]),
        },
        nominal_pc_bar=float(metrics["pc_avg_bar"]) if metrics.get("pc_avg_bar") is not None else None,
        nominal_thrust_avg_n=float(metrics["thrust_avg_n"]) if metrics.get("thrust_avg_n") is not None else None,
        nominal_isp_avg_s=float(metrics["isp_avg_s"]) if metrics.get("isp_avg_s") is not None else None,
        nominal_burn_time_s=float(metrics["burn_time_actual_s"]) if metrics.get("burn_time_actual_s") is not None else None,
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
        engine_state=state.to_dict(),
        geometry_valid=state.validity.geometry_valid,
        failure_reasons=list(state.diagnostics.failure_reasons),
        solver_report=dict(state.diagnostics.solver_report),
        notes=notes,
    )

    checks = {
        "positive_major_dimensions": {
            "passed": all(
                value > 0.0
                for value in (
                    chamber_id_m,
                    injector_face_diameter_m,
                    grain_length_m,
                    port_radius_initial_m,
                    grain_outer_radius_m,
                    throat_diameter_m,
                    nozzle_exit_diameter_m,
                )
            ),
            "hard": True,
            "value": {
                "chamber_id_m": chamber_id_m,
                "grain_length_m": grain_length_m,
                "throat_diameter_m": throat_diameter_m,
                "nozzle_exit_diameter_m": nozzle_exit_diameter_m,
            },
            "limit": "> 0",
            "note": "All frozen diameters, radii, and lengths must remain positive.",
        },
        "geometry_valid": {
            "passed": state.validity.geometry_valid,
            "hard": True,
            "value": state.validity.geometry_valid,
            "limit": {"required": True},
            "note": "Canonical geometry must satisfy all hard packaging, web, L*, and nozzle constraints.",
        }
    }
    return replace(
        geometry,
        checks=checks,
        geometry_valid=state.validity.geometry_valid,
        warnings=list(state.diagnostics.warnings),
        notes=[
            *geometry.notes,
            (
                "Nozzle contour frozen as a conical converging-throat-diverging profile with a finite throat blend "
                f"(r_blend={geometry_state.throat_blend_radius_m * 1000.0:.1f} mm, "
                f"alpha={geometry_state.converging_half_angle_deg:.1f} deg half-angle, "
                f"beta={geometry_state.diverging_half_angle_deg:.1f} deg half-angle)."
            ),
        ],
    )
