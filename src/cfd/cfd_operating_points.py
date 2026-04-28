"""Selection of CFD operating points from existing reduced-order workflow outputs."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from src.cfd.cfd_types import CfdOperatingPoint, CfdTargetDefinition
from src.nozzle_offdesign.expansion_state import exit_to_ambient_ratio
from src.nozzle_offdesign.nozzle_offdesign_types import NozzleOffDesignResult, NozzleOperatingPoint
from src.sizing.geometry_types import GeometryDefinition
from src.thermal.thermal_types import ThermalSizingResult


def _history_array(history: Mapping[str, Any], key: str, fallback_key: str | None = None, *, scale: float = 1.0) -> np.ndarray:
    if key in history:
        return np.asarray(history[key], dtype=float) * scale
    if fallback_key is not None and fallback_key in history:
        return np.asarray(history[fallback_key], dtype=float) * scale
    return np.array([], dtype=float)


def _reference_chamber_temperature_k(geometry: GeometryDefinition) -> float | None:
    if geometry.cea_reference and geometry.cea_reference.get("chamber_temperature_k") is not None:
        return float(geometry.cea_reference["chamber_temperature_k"])
    return None


def _point_from_history_index(
    *,
    operating_point_name: str,
    source_stage: str,
    history: Mapping[str, Any],
    index: int,
    geometry: GeometryDefinition,
    ambient_pressure_pa: float | None,
    notes: Sequence[str],
) -> CfdOperatingPoint:
    time_s = _history_array(history, "t_s")
    pc_pa = _history_array(history, "pc_pa")
    p_inj_in_pa = _history_array(
        history,
        "injector_inlet_pressure_pa",
        "injector_inlet_pressure_bar",
        scale=1.0 if "injector_inlet_pressure_pa" in history else 1.0e5,
    )
    mdot_total = _history_array(history, "mdot_total_kg_s")
    mdot_ox = _history_array(history, "mdot_ox_kg_s")
    mdot_f = _history_array(history, "mdot_f_kg_s")
    return CfdOperatingPoint(
        operating_point_name=operating_point_name,
        source_stage=source_stage,
        time_s=None if time_s.size == 0 else float(time_s[index]),
        chamber_pressure_pa=None if pc_pa.size == 0 else float(pc_pa[index]),
        injector_inlet_pressure_pa=None if p_inj_in_pa.size == 0 else float(p_inj_in_pa[index]),
        mass_flow_kg_s=None if mdot_total.size == 0 else float(mdot_total[index]),
        oxidizer_mass_flow_kg_s=None if mdot_ox.size == 0 else float(mdot_ox[index]),
        fuel_mass_flow_kg_s=None if mdot_f.size == 0 else float(mdot_f[index]),
        chamber_temp_k=_reference_chamber_temperature_k(geometry),
        ambient_pressure_pa=ambient_pressure_pa,
        fluid_properties_reference=f"reduced_order_history:{source_stage}",
        notes=[str(item) for item in notes],
    )


def _average_point_from_history(
    *,
    operating_point_name: str,
    source_stage: str,
    history: Mapping[str, Any],
    geometry: GeometryDefinition,
    ambient_pressure_pa: float | None,
    notes: Sequence[str],
) -> CfdOperatingPoint:
    def _average(values: np.ndarray) -> float | None:
        return None if values.size == 0 else float(np.mean(values))

    time_s = _history_array(history, "t_s")
    return CfdOperatingPoint(
        operating_point_name=operating_point_name,
        source_stage=source_stage,
        time_s=_average(time_s),
        chamber_pressure_pa=_average(_history_array(history, "pc_pa")),
        injector_inlet_pressure_pa=_average(
            _history_array(
                history,
                "injector_inlet_pressure_pa",
                "injector_inlet_pressure_bar",
                scale=1.0 if "injector_inlet_pressure_pa" in history else 1.0e5,
            )
        ),
        mass_flow_kg_s=_average(_history_array(history, "mdot_total_kg_s")),
        oxidizer_mass_flow_kg_s=_average(_history_array(history, "mdot_ox_kg_s")),
        fuel_mass_flow_kg_s=_average(_history_array(history, "mdot_f_kg_s")),
        chamber_temp_k=_reference_chamber_temperature_k(geometry),
        ambient_pressure_pa=ambient_pressure_pa,
        fluid_properties_reference=f"reduced_order_history_average:{source_stage}",
        notes=[str(item) for item in notes],
    )


def _hot_and_cold_corner_points(
    corner_payload: Mapping[str, Any] | None,
    *,
    geometry: GeometryDefinition,
    ambient_pressure_pa: float | None,
) -> list[CfdOperatingPoint]:
    if corner_payload is None:
        return []
    candidates = []
    for item in corner_payload.get("corners", []):
        history = item["result"]["history"]
        pc_pa = _history_array(history, "pc_pa")
        if pc_pa.size == 0:
            continue
        peak_index = int(np.argmax(pc_pa))
        candidates.append((float(pc_pa[peak_index]), item["case_name"], history, peak_index))
    if not candidates:
        return []

    hot = max(candidates, key=lambda item: item[0])
    cold = min(candidates, key=lambda item: item[0])
    points = [
        _point_from_history_index(
            operating_point_name="hot_corner_peak_pc",
            source_stage="hot_corner",
            history=hot[2],
            index=hot[3],
            geometry=geometry,
            ambient_pressure_pa=ambient_pressure_pa,
            notes=[f"Selected from corner case '{hot[1]}' at its peak chamber pressure."],
        )
    ]
    if cold[1] != hot[1]:
        points.append(
            _point_from_history_index(
                operating_point_name="cold_corner_peak_pc",
                source_stage="cold_corner",
                history=cold[2],
                index=cold[3],
                geometry=geometry,
                ambient_pressure_pa=ambient_pressure_pa,
                notes=[f"Selected from corner case '{cold[1]}' at its peak chamber pressure."],
            )
        )
    return points


def _point_from_nozzle_operating_point(
    *,
    operating_point_name: str,
    source_stage: str,
    point: NozzleOperatingPoint,
    notes: Sequence[str],
) -> CfdOperatingPoint:
    return CfdOperatingPoint(
        operating_point_name=operating_point_name,
        source_stage=source_stage,
        time_s=None if point.time_s is None else float(point.time_s),
        chamber_pressure_pa=float(point.chamber_pressure_pa),
        injector_inlet_pressure_pa=None,
        mass_flow_kg_s=float(point.total_mass_flow_kg_s),
        oxidizer_mass_flow_kg_s=None,
        fuel_mass_flow_kg_s=None,
        chamber_temp_k=None if point.chamber_temp_k is None else float(point.chamber_temp_k),
        ambient_pressure_pa=float(point.ambient_pressure_pa),
        fluid_properties_reference="nozzle_offdesign_operating_point",
        notes=[str(item) for item in notes],
    )


def _worst_ground_nozzle_point(nozzle_result: NozzleOffDesignResult) -> CfdOperatingPoint | None:
    ground_evaluations = [
        evaluation
        for evaluation in nozzle_result.ambient_case_results
        if evaluation.summary.environment_type in {"sea_level_static", "ground_test"}
    ]
    candidates: list[tuple[float, NozzleOperatingPoint]] = []
    for evaluation in ground_evaluations:
        for point in evaluation.operating_points:
            ratio = exit_to_ambient_ratio(point.exit_pressure_pa, point.ambient_pressure_pa)
            if ratio is None:
                continue
            candidates.append((ratio, point))
    if not candidates:
        return None
    worst = min(candidates, key=lambda item: item[0])[1]
    return _point_from_nozzle_operating_point(
        operating_point_name="worst_ground_overexpansion",
        source_stage="startup" if (worst.time_s or 0.0) <= 0.0 else "nominal_0d",
        point=worst,
        notes=["Selected as the minimum exit-to-ambient pressure-ratio point in the ground-relevant nozzle off-design set."],
    )


def _matched_altitude_nozzle_point(nozzle_result: NozzleOffDesignResult) -> CfdOperatingPoint | None:
    matched = nozzle_result.matched_altitude_summary
    if matched is None:
        return None
    for evaluation in nozzle_result.ambient_case_results:
        if evaluation.summary.case_name != matched.case_name or not evaluation.operating_points:
            continue
        point = max(evaluation.operating_points, key=lambda item: item.thrust_n)
        return _point_from_nozzle_operating_point(
            operating_point_name="matched_altitude_case",
            source_stage="nominal_0d",
            point=point,
            notes=["Selected from the nozzle environment summary closest to matched expansion."],
        )
    return None


def _startup_and_shutdown_nozzle_points(nozzle_result: NozzleOffDesignResult) -> list[CfdOperatingPoint]:
    ground_evaluations = [
        evaluation
        for evaluation in nozzle_result.ambient_case_results
        if evaluation.summary.environment_type in {"sea_level_static", "ground_test"}
    ]
    if not ground_evaluations:
        return []
    selected = min(
        ground_evaluations,
        key=lambda evaluation: min(
            (
                exit_to_ambient_ratio(point.exit_pressure_pa, point.ambient_pressure_pa)
                for point in evaluation.operating_points
                if point.ambient_pressure_pa > 0.0
            ),
            default=float("inf"),
        ),
    )
    if not selected.operating_points:
        return []
    startup = selected.operating_points[0]
    shutdown = selected.operating_points[-1]
    points = [
        _point_from_nozzle_operating_point(
            operating_point_name="startup_ground_case",
            source_stage="startup",
            point=startup,
            notes=["Selected as the first ground-relevant nozzle off-design operating point."],
        )
    ]
    if shutdown.operating_point_label != startup.operating_point_label:
        points.append(
            _point_from_nozzle_operating_point(
                operating_point_name="shutdown_ground_case",
                source_stage="shutdown",
                point=shutdown,
                notes=["Selected as the last ground-relevant nozzle off-design operating point."],
            )
        )
    return points


def select_operating_points_for_target(
    target: CfdTargetDefinition,
    *,
    cfd_config: Mapping[str, Any],
    geometry: GeometryDefinition,
    nominal_payload: Mapping[str, Any],
    corner_payload: Mapping[str, Any] | None = None,
    ballistics_payload: Mapping[str, Any] | None = None,
    nozzle_result: NozzleOffDesignResult | None = None,
    thermal_result: ThermalSizingResult | None = None,
) -> tuple[list[CfdOperatingPoint], list[str]]:
    """Select the CFD operating points that matter for one target definition."""

    warnings: list[str] = []
    nominal_history = nominal_payload["result"]["history"]
    ambient_pressure_pa = float(nominal_payload["result"]["runtime"]["simulation"].ambient_pressure_pa)
    ballistics_history = None if ballistics_payload is None else ballistics_payload["result"]["history"]
    points: list[CfdOperatingPoint] = []

    if target.target_category == "injector_plenum":
        points.append(
            _point_from_history_index(
                operating_point_name="nominal_initial",
                source_stage="nominal_0d",
                history=nominal_history,
                index=0,
                geometry=geometry,
                ambient_pressure_pa=ambient_pressure_pa,
                notes=["Nominal initial injector operating point from the 0D solver."],
            )
        )
        if bool(cfd_config.get("include_nominal_average_point", True)):
            points.append(
                _average_point_from_history(
                    operating_point_name="nominal_average",
                    source_stage="nominal_0d",
                    history=nominal_history,
                    geometry=geometry,
                    ambient_pressure_pa=ambient_pressure_pa,
                    notes=["Average injector operating point from the 0D solver."],
                )
            )
        dp_history = _history_array(
            nominal_history,
            "injector_delta_p_pa",
            "injector_delta_p_bar",
            scale=1.0 if "injector_delta_p_pa" in nominal_history else 1.0e5,
        )
        if dp_history.size:
            points.append(
                _point_from_history_index(
                    operating_point_name="peak_injector_dp",
                    source_stage="nominal_0d",
                    history=nominal_history,
                    index=int(np.argmax(dp_history)),
                    geometry=geometry,
                    ambient_pressure_pa=ambient_pressure_pa,
                    notes=["Maximum injector delta-p point from the nominal 0D history."],
                )
            )
        if bool(cfd_config.get("include_hot_cold_corner_points", True)):
            points.extend(_hot_and_cold_corner_points(corner_payload, geometry=geometry, ambient_pressure_pa=ambient_pressure_pa))

    elif target.target_category == "headend_prechamber":
        points.append(
            _point_from_history_index(
                operating_point_name="nominal_initial",
                source_stage="nominal_0d",
                history=nominal_history,
                index=0,
                geometry=geometry,
                ambient_pressure_pa=ambient_pressure_pa,
                notes=["Nominal initial point used to anchor head-end flow structure."],
            )
        )
        source_history = ballistics_history if ballistics_history else nominal_history
        source_stage = "transient_1d" if ballistics_history else "nominal_0d"
        mdot_ox_history = _history_array(source_history, "mdot_ox_kg_s")
        if mdot_ox_history.size:
            points.append(
                _point_from_history_index(
                    operating_point_name="peak_oxidizer_flow",
                    source_stage=source_stage,
                    history=source_history,
                    index=int(np.argmax(mdot_ox_history)),
                    geometry=geometry,
                    ambient_pressure_pa=ambient_pressure_pa,
                    notes=["Maximum oxidizer-flow point selected for head-end loading sensitivity."],
                )
            )
        pc_history = _history_array(source_history, "pc_pa")
        if pc_history.size:
            points.append(
                _point_from_history_index(
                    operating_point_name="peak_pc",
                    source_stage=source_stage,
                    history=source_history,
                    index=int(np.argmax(pc_history)),
                    geometry=geometry,
                    ambient_pressure_pa=ambient_pressure_pa,
                    notes=["Peak chamber-pressure point used as a head-end severity placeholder."],
                )
            )
        if bool(cfd_config.get("include_hot_cold_corner_points", True)):
            corner_points = _hot_and_cold_corner_points(corner_payload, geometry=geometry, ambient_pressure_pa=ambient_pressure_pa)
            if corner_points:
                points.append(corner_points[0])

    elif target.target_category == "nozzle_local":
        if nozzle_result is None:
            warnings.append("No nozzle off-design result was available; nozzle CFD operating-point selection fell back to nominal reduced-order history.")
            points.append(
                _point_from_history_index(
                    operating_point_name="peak_pc",
                    source_stage="nominal_0d",
                    history=nominal_history,
                    index=int(np.argmax(_history_array(nominal_history, "pc_pa"))),
                    geometry=geometry,
                    ambient_pressure_pa=ambient_pressure_pa,
                    notes=["Fallback nozzle CFD point from the nominal 0D peak-pressure condition."],
                )
            )
        else:
            worst_ground = _worst_ground_nozzle_point(nozzle_result)
            if worst_ground is not None:
                points.append(worst_ground)
            if bool(cfd_config.get("include_startup_shutdown_points", True)):
                points.extend(_startup_and_shutdown_nozzle_points(nozzle_result))
            matched = _matched_altitude_nozzle_point(nozzle_result)
            if matched is not None:
                points.append(matched)

    else:
        source_history = ballistics_history if ballistics_history else nominal_history
        source_stage = "transient_1d" if ballistics_history else "nominal_0d"
        pc_history = _history_array(source_history, "pc_pa")
        if bool(cfd_config.get("include_nominal_average_point", True)):
            points.append(
                _average_point_from_history(
                    operating_point_name="nominal_average",
                    source_stage=source_stage,
                    history=source_history,
                    geometry=geometry,
                    ambient_pressure_pa=ambient_pressure_pa,
                    notes=["Average operating point for late-stage reacting-internal CFD planning."],
                )
            )
        if pc_history.size:
            points.append(
                _point_from_history_index(
                    operating_point_name="peak_pc",
                    source_stage=source_stage,
                    history=source_history,
                    index=int(np.argmax(pc_history)),
                    geometry=geometry,
                    ambient_pressure_pa=ambient_pressure_pa,
                    notes=["Peak chamber-pressure point for the late-stage reacting CFD placeholder."],
                )
            )
        if bool(cfd_config.get("include_hot_cold_corner_points", True)):
            corner_points = _hot_and_cold_corner_points(corner_payload, geometry=geometry, ambient_pressure_pa=ambient_pressure_pa)
            if corner_points:
                points.append(corner_points[0])
        if thermal_result is not None and thermal_result.governing_load_case.time_s:
            points.append(
                CfdOperatingPoint(
                    operating_point_name="worst_thermal_case",
                    source_stage=thermal_result.governing_load_case.source_stage,
                    time_s=float(thermal_result.governing_load_case.time_s[0]),
                    chamber_pressure_pa=float(thermal_result.governing_load_case.chamber_pressure_pa_time[0]),
                    injector_inlet_pressure_pa=None,
                    mass_flow_kg_s=float(thermal_result.governing_load_case.mdot_total_kg_s_time[0]),
                    oxidizer_mass_flow_kg_s=float(thermal_result.governing_load_case.mdot_ox_kg_s_time[0]),
                    fuel_mass_flow_kg_s=float(thermal_result.governing_load_case.mdot_f_kg_s_time[0]),
                    chamber_temp_k=float(thermal_result.governing_load_case.chamber_temp_k_time[0]),
                    ambient_pressure_pa=float(thermal_result.governing_load_case.ambient_pressure_pa),
                    fluid_properties_reference="thermal_governing_case",
                    notes=[
                        f"Derived from thermal governing case '{thermal_result.governing_load_case.case_name}'.",
                        "Use this only if later reacting CFD needs to target a thermally severe portion of the burn.",
                    ],
                )
            )

    deduped: list[CfdOperatingPoint] = []
    seen_names: set[str] = set()
    for point in points:
        if point.operating_point_name in seen_names:
            continue
        seen_names.add(point.operating_point_name)
        deduped.append(point)
    return deduped, warnings
