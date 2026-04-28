"""Injector geometry synthesis and reduced-order runtime integration."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from src.blowdown_hybrid.models import InjectorConfig

from src.injector_design.injector_backcalc import (
    estimate_discharge_coefficient,
    estimate_effective_injector_from_geometry,
)
from src.injector_design.injector_checks import evaluate_injector_checks
from src.injector_design.injector_types import (
    InjectorCandidateEvaluation,
    InjectorDesignPoint,
    InjectorGeometryDefinition,
    InjectorRequirement,
)
from src.injector_design.plenum_init import initialize_plenum_placeholder
from src.injector_design.showerhead_layout import generate_showerhead_layout
from src.io_utils import load_json
from src.sizing.geometry_rules import area_from_diameter, diameter_from_area
from src.sizing.geometry_types import GeometryDefinition


def _policy(config: Mapping[str, Any]) -> dict[str, Any]:
    if "injector_design" in config and isinstance(config["injector_design"], Mapping):
        return dict(config["injector_design"])
    if "injector_geometry" in config and isinstance(config["injector_geometry"], Mapping):
        return dict(config["injector_geometry"])
    return dict(config)


def _coerce_design_point(payload: InjectorDesignPoint | Mapping[str, Any]) -> InjectorDesignPoint:
    if isinstance(payload, InjectorDesignPoint):
        return payload
    normalized = dict(payload)
    normalized["source"] = str(normalized.get("source", "user_override"))
    normalized["notes"] = list(normalized.get("notes", []))
    for key in (
        "mdot_ox_kg_s",
        "injector_inlet_pressure_pa",
        "chamber_pressure_pa",
        "injector_delta_p_pa",
        "liquid_density_kg_m3",
    ):
        normalized[key] = float(normalized[key])
    for key in ("tank_pressure_pa", "time_s"):
        if normalized.get(key) is not None:
            normalized[key] = float(normalized[key])
    return InjectorDesignPoint(**normalized)


def _coerce_requirement(payload: InjectorRequirement | Mapping[str, Any]) -> InjectorRequirement:
    if isinstance(payload, InjectorRequirement):
        return payload
    normalized = dict(payload)
    normalized["source"] = str(normalized.get("source", "equivalent_injector_requirement"))
    for key in (
        "required_total_area_m2",
        "required_effective_cda_m2",
        "assumed_cd",
        "design_mdot_ox_kg_s",
        "design_delta_p_pa",
        "liquid_density_kg_m3",
    ):
        normalized[key] = float(normalized[key])
    return InjectorRequirement(**normalized)


def load_injector_geometry_definition(path: str | Path) -> InjectorGeometryDefinition:
    """Load a synthesized injector geometry definition from JSON."""

    return InjectorGeometryDefinition.from_mapping(load_json(path))


def _integration_axis(time_s: np.ndarray, dt_s: float) -> np.ndarray:
    if time_s.size == 0:
        return np.array([], dtype=float)
    return np.append(time_s, time_s[-1] + dt_s)


def _time_weighted_average(values: np.ndarray, time_s: np.ndarray, dt_s: float) -> float:
    if values.size == 0 or time_s.size == 0:
        return float("nan")
    axis = _integration_axis(time_s, dt_s)
    duration_s = float(axis[-1] - axis[0])
    if duration_s <= 0.0:
        return float(values[-1])
    return float(np.trapezoid(np.append(values, values[-1]), axis) / duration_s)


def _design_point_from_user_override(policy: Mapping[str, Any]) -> InjectorDesignPoint:
    raw = dict(policy.get("user_design_point", {}))
    required = (
        "mdot_ox_kg_s",
        "chamber_pressure_pa",
        "injector_delta_p_pa",
        "liquid_density_kg_m3",
    )
    missing = [key for key in required if raw.get(key) is None]
    if missing:
        raise ValueError(
            "injector_geometry.user_design_point must define "
            + ", ".join(missing)
            + " when design_condition_source='user_override'."
        )
    chamber_pressure_pa = float(raw["chamber_pressure_pa"])
    injector_delta_p_pa = float(raw["injector_delta_p_pa"])
    injector_inlet_pressure_pa = float(raw.get("injector_inlet_pressure_pa", chamber_pressure_pa + injector_delta_p_pa))
    return InjectorDesignPoint(
        source="user_override",
        mdot_ox_kg_s=float(raw["mdot_ox_kg_s"]),
        injector_inlet_pressure_pa=injector_inlet_pressure_pa,
        chamber_pressure_pa=chamber_pressure_pa,
        injector_delta_p_pa=injector_delta_p_pa,
        liquid_density_kg_m3=float(raw["liquid_density_kg_m3"]),
        tank_pressure_pa=float(raw["tank_pressure_pa"]) if raw.get("tank_pressure_pa") is not None else injector_inlet_pressure_pa,
        time_s=float(raw["time_s"]) if raw.get("time_s") is not None else None,
        notes=["Injector synthesis design point taken from injector_geometry.user_design_point."],
    )


def _baseline_runtime(config: Mapping[str, Any], raw_cea_config: Mapping[str, Any] | None) -> dict[str, Any]:
    from src.simulation.solver_0d import prepare_runtime_case

    return prepare_runtime_case(
        config,
        raw_cea_config=raw_cea_config,
        injector_source_override="equivalent_manual",
    )["runtime"]


def _nominal_payload_for_design_point(config: Mapping[str, Any], raw_cea_config: Mapping[str, Any] | None) -> dict[str, Any]:
    from src.simulation.case_runner import run_nominal_case

    return run_nominal_case(
        config,
        injector_source_override="equivalent_manual",
        raw_cea_config=raw_cea_config,
    )


def _design_point_from_runtime(runtime: Mapping[str, Any], source: str) -> InjectorDesignPoint:
    derived = runtime["derived"]
    tank_state = runtime["tank_initial_state"]
    chamber_pressure_pa = float(runtime["design_point"].chamber_pressure_pa)
    injector_inlet_pressure_pa = float(derived["design_injector_inlet_pressure_bar"]) * 1.0e5
    injector_delta_p_pa = float(derived["design_injector_delta_p_bar"]) * 1.0e5
    return InjectorDesignPoint(
        source=source,
        mdot_ox_kg_s=float(derived["target_mdot_ox_kg_s"]),
        injector_inlet_pressure_pa=injector_inlet_pressure_pa,
        chamber_pressure_pa=chamber_pressure_pa,
        injector_delta_p_pa=injector_delta_p_pa,
        liquid_density_kg_m3=float(tank_state.rho_l_kg_m3),
        tank_pressure_pa=float(tank_state.p_pa),
        time_s=0.0,
        notes=["Injector synthesis design point uses the nominal initial equivalent-injector operating point."],
    )


def _design_point_from_history(
    nominal_payload: Mapping[str, Any],
    *,
    source: str,
) -> InjectorDesignPoint:
    result = nominal_payload["result"]
    history = result["history"]
    raw_history = result.get("raw_history", {})
    runtime = result["runtime"]
    time_s = np.asarray(raw_history.get("time_s", history.get("t_s", [])), dtype=float)
    dt_s = float(runtime["simulation"].dt_s)
    mdot_ox = np.asarray(raw_history["mdot_ox_kg_s"], dtype=float)
    p_inj_in_pa = np.asarray(raw_history["p_inj_in_pa"], dtype=float)
    pc_pa = np.asarray(raw_history["pc_pa"], dtype=float)
    dp_inj_pa = np.asarray(raw_history["dp_inj_pa"], dtype=float)
    rho_liq_kg_m3 = np.asarray(raw_history["rho_liq_kg_m3"], dtype=float)
    tank_p_pa = np.asarray(raw_history["tank_p_pa"], dtype=float)

    if source == "nominal_average":
        return InjectorDesignPoint(
            source=source,
            mdot_ox_kg_s=_time_weighted_average(mdot_ox, time_s, dt_s),
            injector_inlet_pressure_pa=_time_weighted_average(p_inj_in_pa, time_s, dt_s),
            chamber_pressure_pa=_time_weighted_average(pc_pa, time_s, dt_s),
            injector_delta_p_pa=_time_weighted_average(dp_inj_pa, time_s, dt_s),
            liquid_density_kg_m3=_time_weighted_average(rho_liq_kg_m3, time_s, dt_s),
            tank_pressure_pa=_time_weighted_average(tank_p_pa, time_s, dt_s),
            notes=[
                "Injector synthesis design point uses time-weighted averages from the nominal 0D run.",
                "Averages are based on the equivalent-injector baseline, not the synthesized geometry.",
            ],
        )

    hot_index = int(np.argmax(mdot_ox))
    return InjectorDesignPoint(
        source=source,
        mdot_ox_kg_s=float(mdot_ox[hot_index]),
        injector_inlet_pressure_pa=float(p_inj_in_pa[hot_index]),
        chamber_pressure_pa=float(pc_pa[hot_index]),
        injector_delta_p_pa=float(dp_inj_pa[hot_index]),
        liquid_density_kg_m3=float(rho_liq_kg_m3[hot_index]),
        tank_pressure_pa=float(tank_p_pa[hot_index]),
        time_s=float(time_s[hot_index]) if time_s.size else None,
        notes=[
            "Injector synthesis design point uses the nominal 0D time sample with the highest oxidizer mass flow.",
            "This is a deterministic hot-case placeholder for later cold-flow or CFD-informed refinement.",
        ],
    )


def resolve_injector_design_point(
    config: Mapping[str, Any],
    *,
    nominal_payload: Mapping[str, Any] | None = None,
    raw_cea_config: Mapping[str, Any] | None = None,
) -> InjectorDesignPoint:
    """Resolve the explicit design condition used to size the showerhead geometry."""

    policy = _policy(config)
    source = str(policy.get("design_condition_source", "nominal_initial"))
    if source == "user_override":
        return _design_point_from_user_override(policy)

    runtime = _baseline_runtime(config, raw_cea_config)
    if source == "nominal_initial":
        return _design_point_from_runtime(runtime, source)

    payload = nominal_payload if nominal_payload is not None else _nominal_payload_for_design_point(config, raw_cea_config)
    if source not in {"nominal_average", "hot_case"}:
        raise ValueError(
            "injector_geometry.design_condition_source must be one of "
            "'nominal_initial', 'nominal_average', 'hot_case', or 'user_override'."
        )
    return _design_point_from_history(payload, source=source)


def _build_injector_requirement(
    config: Mapping[str, Any],
    engine_geometry: GeometryDefinition,
    design_point: InjectorDesignPoint,
    *,
    raw_cea_config: Mapping[str, Any] | None = None,
) -> InjectorRequirement:
    runtime = _baseline_runtime(config, raw_cea_config)
    assumed_cd = float(runtime["injector"].cd)
    design_delta_p_pa = max(float(design_point.injector_delta_p_pa), 1.0e-9)
    liquid_density_kg_m3 = max(float(design_point.liquid_density_kg_m3), 1.0e-9)
    required_effective_cda_m2 = float(design_point.mdot_ox_kg_s) / math.sqrt(2.0 * liquid_density_kg_m3 * design_delta_p_pa)
    required_total_area_m2 = required_effective_cda_m2 / max(assumed_cd, 1.0e-9)

    baseline_area_m2 = float(engine_geometry.injector_equivalent_area_m2)
    if baseline_area_m2 > 0.0:
        baseline_cda_m2 = baseline_area_m2 * assumed_cd
        area_error = abs(required_total_area_m2 - baseline_area_m2) / baseline_area_m2
        if area_error <= 0.02:
            required_total_area_m2 = baseline_area_m2
            required_effective_cda_m2 = baseline_cda_m2

    return InjectorRequirement(
        source=f"equivalent_{design_point.source}",
        required_total_area_m2=required_total_area_m2,
        required_effective_cda_m2=required_effective_cda_m2,
        assumed_cd=assumed_cd,
        design_mdot_ox_kg_s=float(design_point.mdot_ox_kg_s),
        design_delta_p_pa=float(design_point.injector_delta_p_pa),
        liquid_density_kg_m3=float(design_point.liquid_density_kg_m3),
    )


def _diameter_penalty(hole_diameter_mm: float, preferred_band_mm: tuple[float, float]) -> float:
    lower_mm, upper_mm = preferred_band_mm
    if lower_mm <= hole_diameter_mm <= upper_mm:
        return 0.0
    if hole_diameter_mm < lower_mm:
        return (lower_mm - hole_diameter_mm) / max(lower_mm, 1.0e-6)
    return (hole_diameter_mm - upper_mm) / max(upper_mm, 1.0e-6)


def _ld_penalty(hole_ld_ratio: float, target_band: tuple[float, float]) -> float:
    lower, upper = target_band
    if lower <= hole_ld_ratio <= upper:
        return 0.0
    if hole_ld_ratio < lower:
        return (lower - hole_ld_ratio) / max(lower, 1.0e-6)
    return (hole_ld_ratio - upper) / max(upper, 1.0e-6)


def _velocity_penalty(design_hole_velocity_m_s: float, max_velocity_m_s: float) -> float:
    if design_hole_velocity_m_s <= max_velocity_m_s:
        return 0.0
    return (design_hole_velocity_m_s - max_velocity_m_s) / max(max_velocity_m_s, 1.0e-6)


def _coerce_candidate_sort_key(candidate: InjectorCandidateEvaluation) -> tuple[int, float, int]:
    return (0 if candidate.valid else 1, float(candidate.score), int(candidate.hole_count))


def _assemble_geometry(
    *,
    engine_geometry: GeometryDefinition,
    policy: Mapping[str, Any],
    design_point: InjectorDesignPoint,
    requirement: InjectorRequirement,
    hole_count: int,
    hole_diameter_m: float,
    plate_outer_diameter_m: float,
    active_face_diameter_m: float,
    ring_definitions: list[Any],
    center_hole_enabled: bool,
    min_ligament_m: float,
    min_edge_margin_m: float,
    notes: list[str] | None = None,
) -> InjectorGeometryDefinition:
    plate_thickness_m = float(policy["preferred_plate_thickness_mm"]) * 1.0e-3
    if plate_thickness_m <= 0.0:
        plate_thickness_m = float(engine_geometry.injector_plate_thickness_m)
    area_per_hole_m2 = area_from_diameter(hole_diameter_m)
    total_geometric_area_m2 = float(hole_count) * area_per_hole_m2
    hole_ld_ratio = plate_thickness_m / max(float(hole_diameter_m), 1.0e-12)
    estimated_cd, cd_notes = estimate_discharge_coefficient(
        hole_ld_ratio=hole_ld_ratio,
        default_cd=float(policy["default_injector_cd"]),
        edge_model=str(policy["discharge_edge_model"]),
        backcalculation_mode=str(policy["backcalculation_mode"]),
    )
    plenum = initialize_plenum_placeholder(policy, engine_geometry, active_face_diameter_m=active_face_diameter_m)
    active_face_area_m2 = area_from_diameter(active_face_diameter_m)
    design_hole_velocity_m_s = float(design_point.mdot_ox_kg_s) / max(
        float(design_point.liquid_density_kg_m3) * total_geometric_area_m2,
        1.0e-12,
    )

    return InjectorGeometryDefinition(
        injector_type=str(policy["injector_type"]),
        design_condition_source=design_point.source,
        requirement_source=requirement.source,
        plate_outer_diameter_m=plate_outer_diameter_m,
        active_face_diameter_m=active_face_diameter_m,
        plate_thickness_m=plate_thickness_m,
        hole_count=int(hole_count),
        hole_diameter_m=float(hole_diameter_m),
        area_per_hole_m2=area_per_hole_m2,
        total_geometric_area_m2=total_geometric_area_m2,
        estimated_cd=estimated_cd,
        estimated_effective_area_m2=total_geometric_area_m2,
        estimated_effective_cda_m2=estimated_cd * total_geometric_area_m2,
        required_total_area_m2=float(requirement.required_total_area_m2),
        required_effective_cda_m2=float(requirement.required_effective_cda_m2),
        actual_to_required_area_ratio=total_geometric_area_m2 / max(float(requirement.required_total_area_m2), 1.0e-12),
        actual_to_required_cda_ratio=(estimated_cd * total_geometric_area_m2)
        / max(float(requirement.required_effective_cda_m2), 1.0e-12),
        hole_ld_ratio=hole_ld_ratio,
        ring_count=len(ring_definitions),
        ring_definitions=list(ring_definitions),
        center_hole_enabled=bool(center_hole_enabled),
        min_ligament_m=float(min_ligament_m),
        min_edge_margin_m=float(min_edge_margin_m),
        plate_to_active_face_margin_m=0.5 * max(plate_outer_diameter_m - active_face_diameter_m, 0.0),
        plenum_depth_m=float(plenum["plenum_depth_m"]),
        plenum_diameter_m=float(plenum["plenum_diameter_m"]),
        plenum_volume_m3=float(plenum["plenum_volume_m3"]),
        face_to_grain_distance_m=float(plenum["face_to_grain_distance_m"]),
        discharges_into_prechamber=bool(plenum["discharges_into_prechamber"]),
        design_mdot_ox_kg_s=float(design_point.mdot_ox_kg_s),
        design_liquid_density_kg_m3=float(design_point.liquid_density_kg_m3),
        design_injector_delta_p_pa=float(design_point.injector_delta_p_pa),
        design_injector_inlet_pressure_pa=float(design_point.injector_inlet_pressure_pa),
        design_chamber_pressure_pa=float(design_point.chamber_pressure_pa),
        design_hole_velocity_m_s=design_hole_velocity_m_s,
        geometric_open_area_ratio=total_geometric_area_m2 / max(active_face_area_m2, 1.0e-12),
        discharge_edge_model=str(policy["discharge_edge_model"]),
        backcalculation_mode=str(policy["backcalculation_mode"]),
        injector_geometry_valid=True,
        checks={},
        warnings=[],
        notes=[*(notes or []), *cd_notes],
        failure_reason=None,
    )


def _candidate_score(
    geometry: InjectorGeometryDefinition,
    *,
    preferred_hole_diameter_range_mm: tuple[float, float],
    target_hole_ld_band: tuple[float, float],
    max_velocity_m_s: float,
    valid: bool,
) -> float:
    hole_diameter_mm = geometry.hole_diameter_m * 1000.0
    score = 100.0 * abs(geometry.actual_to_required_cda_ratio - 1.0)
    score += 20.0 * abs(geometry.actual_to_required_area_ratio - 1.0)
    score += 8.0 * _diameter_penalty(hole_diameter_mm, preferred_hole_diameter_range_mm)
    score += 5.0 * _ld_penalty(geometry.hole_ld_ratio, target_hole_ld_band)
    score += 5.0 * _velocity_penalty(geometry.design_hole_velocity_m_s, max_velocity_m_s)
    score += 0.15 * float(geometry.ring_count)
    if not valid:
        score += 1_000.0
    return score


def _candidate_evaluation(
    geometry: InjectorGeometryDefinition,
    *,
    score: float,
    valid: bool,
    failure_reason: str | None = None,
) -> InjectorCandidateEvaluation:
    return InjectorCandidateEvaluation(
        hole_count=geometry.hole_count,
        hole_diameter_m=geometry.hole_diameter_m,
        ring_count=geometry.ring_count,
        center_hole_enabled=geometry.center_hole_enabled,
        total_geometric_area_m2=geometry.total_geometric_area_m2,
        estimated_effective_cda_m2=geometry.estimated_effective_cda_m2,
        actual_to_required_area_ratio=geometry.actual_to_required_area_ratio,
        actual_to_required_cda_ratio=geometry.actual_to_required_cda_ratio,
        hole_ld_ratio=geometry.hole_ld_ratio,
        min_ligament_m=geometry.min_ligament_m,
        min_edge_margin_m=geometry.min_edge_margin_m,
        open_area_ratio=geometry.geometric_open_area_ratio,
        design_hole_velocity_m_s=geometry.design_hole_velocity_m_s,
        score=score,
        valid=valid,
        failure_reason=failure_reason,
    )


def _search_candidates(
    policy: Mapping[str, Any],
    engine_geometry: GeometryDefinition,
    design_point: InjectorDesignPoint,
    requirement: InjectorRequirement,
) -> tuple[InjectorGeometryDefinition, list[InjectorCandidateEvaluation]]:
    plate_outer_diameter_m = float(engine_geometry.injector_face_diameter_m)
    active_face_diameter_m = plate_outer_diameter_m * float(policy["active_face_margin_factor"])
    preferred_hole_diameter_range_mm = tuple(float(value) for value in policy["preferred_hole_diameter_range_mm"])
    target_hole_ld_band = (float(policy["target_hole_ld_min"]), float(policy["target_hole_ld_max"]))
    max_velocity_m_s = float(policy["maximum_hole_velocity_m_s"])
    hole_diameter_m = float(policy["fixed_hole_diameter_mm"]) * 1.0e-3
    hole_area_m2 = area_from_diameter(hole_diameter_m)
    hole_count = max(1, int(math.ceil(float(requirement.required_total_area_m2) / max(hole_area_m2, 1.0e-12))))
    notes = [
        "Injector geometry is derived directly from the required oxidizer-hole area and a fixed hole diameter.",
        f"Fixed hole diameter basis: {hole_diameter_m * 1000.0:.3f} mm.",
    ]
    try:
        layout = generate_showerhead_layout(
            hole_count=int(hole_count),
            hole_diameter_m=hole_diameter_m,
            active_face_diameter_m=active_face_diameter_m,
            minimum_ligament_m=float(policy["minimum_ligament_mm"]) * 1.0e-3,
            minimum_edge_margin_m=float(policy["minimum_edge_margin_mm"]) * 1.0e-3,
            allow_center_hole=bool(policy["allow_center_hole"]),
            max_ring_count=int(policy["maximum_ring_count"]),
            spacing_mode=str(policy["preferred_ring_spacing_mode"]),
        )
    except Exception as exc:
        failure_reason = f"layout_solver_error: {exc}"
        provisional = _assemble_geometry(
            engine_geometry=engine_geometry,
            policy=policy,
            design_point=design_point,
            requirement=requirement,
            hole_count=int(hole_count),
            hole_diameter_m=hole_diameter_m,
            plate_outer_diameter_m=plate_outer_diameter_m,
            active_face_diameter_m=active_face_diameter_m,
            ring_definitions=[],
            center_hole_enabled=False,
            min_ligament_m=0.0,
            min_edge_margin_m=0.0,
            notes=notes,
        )
        score = _candidate_score(
            provisional,
            preferred_hole_diameter_range_mm=preferred_hole_diameter_range_mm,
            target_hole_ld_band=target_hole_ld_band,
            max_velocity_m_s=max_velocity_m_s,
            valid=False,
        )
        geometry = replace(
            provisional,
            injector_geometry_valid=False,
            warnings=[*provisional.warnings, failure_reason],
            failure_reason=failure_reason,
        )
        candidate = _candidate_evaluation(geometry, score=score, valid=False, failure_reason=failure_reason)
        return geometry, [candidate]

    failure_reason = layout.failure_reason
    provisional = _assemble_geometry(
        engine_geometry=engine_geometry,
        policy=policy,
        design_point=design_point,
        requirement=requirement,
        hole_count=int(hole_count),
        hole_diameter_m=hole_diameter_m,
        plate_outer_diameter_m=plate_outer_diameter_m,
        active_face_diameter_m=active_face_diameter_m,
        ring_definitions=layout.ring_definitions,
        center_hole_enabled=layout.center_hole_enabled,
        min_ligament_m=layout.min_ligament_m,
        min_edge_margin_m=layout.min_edge_margin_m,
        notes=notes,
    )
    checks, valid, check_warnings = evaluate_injector_checks(provisional, policy, engine_geometry)
    warnings = [*provisional.warnings, *check_warnings]
    if failure_reason is not None:
        valid = False
        warnings.append(failure_reason)
    score = _candidate_score(
        provisional,
        preferred_hole_diameter_range_mm=preferred_hole_diameter_range_mm,
        target_hole_ld_band=target_hole_ld_band,
        max_velocity_m_s=max_velocity_m_s,
        valid=valid,
    )
    geometry = replace(
        provisional,
        injector_geometry_valid=valid,
        checks=checks,
        warnings=warnings,
        failure_reason=failure_reason if not valid else None,
        notes=[
            *provisional.notes,
            "Hole count is the smallest integer count whose realized total hole area meets or exceeds the requirement.",
        ],
    )
    candidate = _candidate_evaluation(geometry, score=score, valid=valid, failure_reason=geometry.failure_reason)
    return geometry, [candidate]


def synthesize_showerhead_injector(
    config: Mapping[str, Any],
    engine_geometry: GeometryDefinition,
    design_point: InjectorDesignPoint | Mapping[str, Any],
    injector_requirement: InjectorRequirement | Mapping[str, Any],
) -> InjectorGeometryDefinition:
    """Synthesize a manufacturable axial showerhead geometry from the equivalent injector requirement."""

    policy = _policy(config)
    if str(policy["injector_type"]) != "axial_showerhead":
        raise ValueError("Only injector_design.injector_type='axial_showerhead' is currently supported.")
    resolved_design_point = _coerce_design_point(design_point)
    resolved_requirement = _coerce_requirement(injector_requirement)
    geometry, _ = _search_candidates(policy, engine_geometry, resolved_design_point, resolved_requirement)
    return geometry


def build_injector_synthesis_case(
    config: Mapping[str, Any],
    engine_geometry: GeometryDefinition,
    *,
    design_point: InjectorDesignPoint | Mapping[str, Any] | None = None,
    nominal_payload: Mapping[str, Any] | None = None,
    raw_cea_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the full injector-design payload from baseline geometry and a chosen design point."""

    resolved_design_point = (
        _coerce_design_point(design_point)
        if design_point is not None
        else resolve_injector_design_point(
            config,
            nominal_payload=nominal_payload,
            raw_cea_config=raw_cea_config,
        )
    )
    requirement = _build_injector_requirement(
        config,
        engine_geometry,
        resolved_design_point,
        raw_cea_config=raw_cea_config,
    )
    injector_geometry, candidates = _search_candidates(_policy(config), engine_geometry, resolved_design_point, requirement)
    effective_model = estimate_effective_injector_from_geometry(
        injector_geometry,
        discharge_model=_policy(config),
    )
    return {
        "design_point": resolved_design_point,
        "requirement": requirement,
        "injector_geometry": injector_geometry,
        "effective_model": effective_model,
        "candidates": candidates,
    }


def resolve_injector_geometry_for_runtime(
    config: Mapping[str, Any],
    *,
    frozen_geometry: GeometryDefinition | None = None,
    injector_geometry: InjectorGeometryDefinition | Mapping[str, Any] | None = None,
    raw_cea_config: Mapping[str, Any] | None = None,
) -> InjectorGeometryDefinition | None:
    """Resolve the runtime injector-geometry override when the solver is set to use geometry back-calculation."""

    policy = _policy(config)
    source = str(policy.get("solver_injector_source", "equivalent_manual"))
    if source == "equivalent_manual":
        return None
    if source != "geometry_backcalculated":
        raise ValueError("injector_geometry.solver_injector_source must be 'equivalent_manual' or 'geometry_backcalculated'.")

    if injector_geometry is not None:
        return (
            injector_geometry
            if isinstance(injector_geometry, InjectorGeometryDefinition)
            else InjectorGeometryDefinition.from_mapping(dict(injector_geometry))
        )

    geometry_path = Path(str(policy.get("geometry_path", "")))
    if geometry_path.exists():
        return load_injector_geometry_definition(geometry_path)

    if frozen_geometry is None:
        raise FileNotFoundError(
            f"Geometry-derived injector mode requested, but injector geometry file was not found: {geometry_path}"
        )

    return build_injector_synthesis_case(
        config,
        frozen_geometry,
        raw_cea_config=raw_cea_config,
    )["injector_geometry"]


def apply_injector_geometry_to_runtime(
    runtime: Mapping[str, Any],
    injector_geometry: InjectorGeometryDefinition | Mapping[str, Any],
    *,
    discharge_model: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Replace the equivalent injector runtime inputs with geometry-derived properties."""

    resolved_geometry = (
        injector_geometry
        if isinstance(injector_geometry, InjectorGeometryDefinition)
        else InjectorGeometryDefinition.from_mapping(dict(injector_geometry))
    )
    fluid_state = {
        "mdot_ox_kg_s": float(runtime["derived"]["target_mdot_ox_kg_s"]),
        "liquid_density_kg_m3": float(runtime["derived"]["design_liquid_density_kg_m3"]),
        "chamber_pressure_pa": float(runtime["design_point"].chamber_pressure_pa),
    }
    effective = estimate_effective_injector_from_geometry(
        resolved_geometry,
        fluid_state=fluid_state,
        discharge_model=discharge_model,
    )
    updated_runtime = deepcopy(dict(runtime))
    updated_runtime["injector"] = replace(
        runtime["injector"],
        cd=float(effective.estimated_cd),
        total_area_m2=float(effective.total_geometric_area_m2),
        hole_count=int(resolved_geometry.hole_count),
    )
    updated_runtime["injector_geometry"] = resolved_geometry
    updated_runtime["injector_effective_model"] = effective
    derived = dict(updated_runtime.get("derived", {}))
    derived.update(
        {
            "injector_source": "geometry_backcalculated",
            "injector_geometry_valid": bool(resolved_geometry.injector_geometry_valid),
            "injector_geometry_warning_count": len(resolved_geometry.warnings),
            "injector_cd": float(effective.estimated_cd),
            "injector_total_area_mm2": float(effective.total_geometric_area_m2) * 1.0e6,
            "injector_effective_cda_mm2": float(effective.effective_cda_m2) * 1.0e6,
            "injector_hole_count": int(resolved_geometry.hole_count),
            "injector_hole_diameter_mm": float(resolved_geometry.hole_diameter_m) * 1000.0,
            "injector_plate_thickness_mm": float(resolved_geometry.plate_thickness_m) * 1000.0,
            "injector_hole_ld_ratio": float(resolved_geometry.hole_ld_ratio),
            "injector_ring_count": int(resolved_geometry.ring_count),
            "injector_open_area_ratio": float(resolved_geometry.geometric_open_area_ratio),
            "injector_min_ligament_mm": float(resolved_geometry.min_ligament_m) * 1000.0,
            "injector_min_edge_margin_mm": float(resolved_geometry.min_edge_margin_m) * 1000.0,
            "injector_design_hole_velocity_m_s": float(effective.design_hole_velocity_m_s),
            "injector_total_area_source": "geometry_backcalculated",
            "injector_geometry_warnings": list(resolved_geometry.warnings),
        }
    )
    updated_runtime["derived"] = derived
    return updated_runtime

