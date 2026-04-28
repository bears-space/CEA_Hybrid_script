"""Structural load-case generation from the existing reduced-order workflow outputs."""

from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np

from src.sizing.geometry_types import GeometryDefinition
from src.structural.structural_types import StructuralLoadCase


def _history_index(history: Mapping[str, Any], mode: str) -> int:
    time_s = np.asarray(history.get("t_s", []), dtype=float)
    if time_s.size == 0:
        raise ValueError("Cannot build a structural load case from an empty history.")
    if mode == "initial":
        return 0
    return int(np.argmax(np.asarray(history["pc_pa"], dtype=float)))


def _value_at(history: Mapping[str, Any], key: str, index: int, default: float = 0.0) -> float:
    values = history.get(key)
    if values is None:
        return float(default)
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        return float(default)
    return float(array[min(max(index, 0), len(array) - 1)])


def _load_case_from_history(
    *,
    case_name: str,
    source_stage: str,
    history: Mapping[str, Any],
    geometry: GeometryDefinition,
    ambient_pressure_pa: float,
    nozzle_force_multiplier: float,
    index_mode: str,
    note: str,
) -> StructuralLoadCase:
    index = _history_index(history, index_mode)
    chamber_pressure_pa = _value_at(history, "pc_pa", index)
    injector_upstream_pressure_pa = _value_at(history, "injector_inlet_pressure_pa", index, chamber_pressure_pa)
    injector_delta_p_pa = _value_at(
        history,
        "injector_delta_p_pa",
        index,
        max(injector_upstream_pressure_pa - chamber_pressure_pa, 0.0),
    )
    feed_delta_p_pa = _value_at(history, "feed_pressure_drop_pa", index, 0.0)
    tank_pressure_pa = _value_at(history, "tank_pressure_pa", index, injector_upstream_pressure_pa + feed_delta_p_pa)
    gauge_pressure_pa = max(chamber_pressure_pa - ambient_pressure_pa, 0.0)
    closure_separating_force_n = gauge_pressure_pa * float(geometry.chamber_cross_section_area_m2)
    nozzle_separating_force_n = gauge_pressure_pa * float(geometry.throat_area_m2) * float(nozzle_force_multiplier)
    axial_force_n = closure_separating_force_n + nozzle_separating_force_n
    return StructuralLoadCase(
        case_name=case_name,
        source_stage=source_stage,
        chamber_pressure_pa=chamber_pressure_pa,
        injector_upstream_pressure_pa=injector_upstream_pressure_pa,
        injector_delta_p_pa=injector_delta_p_pa,
        feed_delta_p_pa=feed_delta_p_pa,
        tank_pressure_pa=tank_pressure_pa,
        ambient_pressure_pa=ambient_pressure_pa,
        axial_force_n=axial_force_n,
        nozzle_separating_force_n=nozzle_separating_force_n,
        closure_separating_force_n=closure_separating_force_n,
        time_s=_value_at(history, "t_s", index, 0.0),
        notes=[note, f"History index: {index}"],
    )


def _user_override_case(
    structural_config: Mapping[str, Any],
    geometry: GeometryDefinition,
) -> StructuralLoadCase:
    override = dict(structural_config.get("user_override_load_case", {}))
    chamber_pressure_pa = float(override["chamber_pressure_pa"])
    ambient_pressure_pa = float(override.get("ambient_pressure_pa", 101325.0))
    gauge_pressure_pa = max(chamber_pressure_pa - ambient_pressure_pa, 0.0)
    closure_force_n = float(
        override.get("closure_separating_force_n", gauge_pressure_pa * float(geometry.chamber_cross_section_area_m2))
    )
    nozzle_force_n = float(
        override.get("nozzle_separating_force_n", gauge_pressure_pa * float(geometry.throat_area_m2))
    )
    axial_force_n = float(override.get("axial_force_n", closure_force_n + nozzle_force_n))
    return StructuralLoadCase(
        case_name=str(override.get("case_name", "user_override")),
        source_stage=str(override.get("source_stage", "user_override")),
        chamber_pressure_pa=chamber_pressure_pa,
        injector_upstream_pressure_pa=float(override.get("injector_upstream_pressure_pa", chamber_pressure_pa)),
        injector_delta_p_pa=float(override.get("injector_delta_p_pa", 0.0)),
        feed_delta_p_pa=float(override.get("feed_delta_p_pa", 0.0)),
        tank_pressure_pa=float(override["tank_pressure_pa"]) if override.get("tank_pressure_pa") is not None else None,
        ambient_pressure_pa=ambient_pressure_pa,
        axial_force_n=axial_force_n,
        nozzle_separating_force_n=nozzle_force_n,
        closure_separating_force_n=closure_force_n,
        time_s=None,
        notes=[str(item) for item in override.get("notes", [])],
    )


def build_structural_load_cases(
    structural_config: Mapping[str, Any],
    geometry: GeometryDefinition,
    *,
    nominal_payload: Mapping[str, Any],
    corner_payload: Mapping[str, Any] | None = None,
    ballistics_payload: Mapping[str, Any] | None = None,
) -> tuple[list[StructuralLoadCase], StructuralLoadCase, list[str]]:
    """Build explicit structural load cases from existing solver results."""

    warnings: list[str] = []
    settings = dict(structural_config)
    nozzle_force_multiplier = float(settings.get("nozzle_mount", {}).get("separating_force_multiplier", 1.0))
    ambient_pressure_pa = float(
        settings.get("user_override_load_case", {}).get(
            "ambient_pressure_pa",
            nominal_payload["result"]["runtime"]["simulation"].ambient_pressure_pa,
        )
    )

    load_cases: list[StructuralLoadCase] = []
    nominal_history = nominal_payload["result"]["history"]
    if settings.get("include_nominal_initial_case", True):
        load_cases.append(
            _load_case_from_history(
                case_name="nominal_initial_0d",
                source_stage="nominal_0d",
                history=nominal_history,
                geometry=geometry,
                ambient_pressure_pa=ambient_pressure_pa,
                nozzle_force_multiplier=nozzle_force_multiplier,
                index_mode="initial",
                note="Initial nominal 0D state.",
            )
        )
    if settings.get("include_nominal_peak_case", True):
        load_cases.append(
            _load_case_from_history(
                case_name="nominal_peak_0d",
                source_stage="nominal_0d",
                history=nominal_history,
                geometry=geometry,
                ambient_pressure_pa=ambient_pressure_pa,
                nozzle_force_multiplier=nozzle_force_multiplier,
                index_mode="peak_pc",
                note="Peak chamber-pressure nominal 0D state.",
            )
        )

    if corner_payload is not None and settings.get("include_corner_case_envelope", True):
        peak_case = None
        peak_pressure = -math.inf
        for item in corner_payload.get("corners", []):
            history = item["result"]["history"]
            if not history:
                continue
            pressure = float(np.max(np.asarray(history.get("pc_pa", []), dtype=float)))
            if pressure > peak_pressure:
                peak_pressure = pressure
                peak_case = item
        if peak_case is not None:
            load_cases.append(
                _load_case_from_history(
                    case_name=f"{peak_case['case_name']}_peak_0d",
                    source_stage="corner_case_envelope",
                    history=peak_case["result"]["history"],
                    geometry=geometry,
                    ambient_pressure_pa=ambient_pressure_pa,
                    nozzle_force_multiplier=nozzle_force_multiplier,
                    index_mode="peak_pc",
                    note=f"Peak chamber-pressure corner case: {peak_case['case_name']}.",
                )
            )
        else:
            warnings.append("Corner-case envelope requested, but no converged corner-case histories were available.")

    if ballistics_payload is not None and settings.get("include_internal_ballistics_peak_case", True):
        history = ballistics_payload["result"]["history"]
        if history:
            load_cases.append(
                _load_case_from_history(
                    case_name="peak_1d",
                    source_stage="peak_1d",
                    history=history,
                    geometry=geometry,
                    ambient_pressure_pa=ambient_pressure_pa,
                    nozzle_force_multiplier=nozzle_force_multiplier,
                    index_mode="peak_pc",
                    note="Peak chamber-pressure quasi-1D state.",
                )
            )
        else:
            warnings.append("Peak-1D structural load source requested, but the internal-ballistics history was empty.")

    if settings["load_source"] == "user_override":
        governing = _user_override_case(settings, geometry)
        load_cases.append(governing)
        return load_cases, governing, warnings

    if not load_cases:
        raise RuntimeError("No structural load cases were generated from the available workflow outputs.")

    if settings["load_source"] == "nominal_0d":
        eligible_cases = [case for case in load_cases if case.source_stage == "nominal_0d"]
    elif settings["load_source"] == "peak_1d":
        eligible_cases = [case for case in load_cases if case.source_stage == "peak_1d"]
    else:
        eligible_cases = [case for case in load_cases if case.source_stage in {"corner_case_envelope", "nominal_0d"}]

    if not eligible_cases:
        warnings.append(
            f"Requested structural load source '{settings['load_source']}' was unavailable; falling back to the highest-pressure available case."
        )
        eligible_cases = list(load_cases)

    governing = max(eligible_cases, key=lambda case: case.chamber_pressure_pa)
    return load_cases, governing, warnings
