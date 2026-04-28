"""Thermal load-case generation from existing reduced-order workflow outputs."""

from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np

from src.sizing.geometry_types import GeometryDefinition
from src.thermal.thermal_types import ThermalLoadCase


def _series(history: Mapping[str, Any], key: str, fallback_value: float) -> list[float]:
    values = history.get(key)
    if values is None:
        time_length = len(history.get("t_s", []))
        return [float(fallback_value)] * time_length
    array = np.asarray(values, dtype=float)
    if array.size == 0:
        time_length = len(history.get("t_s", []))
        return [float(fallback_value)] * time_length
    return [float(value) for value in array]


def _derive_chamber_temperature_history_k(
    *,
    history: Mapping[str, Any],
    geometry: GeometryDefinition,
    thermal_config: Mapping[str, Any],
) -> list[float]:
    default_temp_k = float(thermal_config.get("reference_chamber_temp_k", 3200.0))
    cea_reference = geometry.cea_reference or {}
    reference_temp_k = float(cea_reference.get("chamber_temperature_k", default_temp_k))
    reference_cstar_mps = float(cea_reference.get("cstar_mps", 1500.0))
    temperature_scale_exponent = float(thermal_config.get("temperature_scale_exponent", 0.15))
    cstar_history = _series(history, "cstar_effective_mps", reference_cstar_mps)
    if not cstar_history:
        return []
    return [
        reference_temp_k * max(value / max(reference_cstar_mps, 1.0e-9), 0.5) ** temperature_scale_exponent
        for value in cstar_history
    ]


def _load_case_from_history(
    *,
    case_name: str,
    source_stage: str,
    history: Mapping[str, Any],
    geometry: GeometryDefinition,
    thermal_config: Mapping[str, Any],
    ambient_pressure_pa: float,
    note: str,
) -> ThermalLoadCase:
    time_s = _series(history, "t_s", 0.0)
    if not time_s:
        raise ValueError("Cannot build a thermal load case from an empty history.")
    return ThermalLoadCase(
        case_name=case_name,
        source_stage=source_stage,
        time_series_reference=case_name,
        chamber_pressure_pa_time=_series(history, "pc_pa", 0.0),
        mdot_total_kg_s_time=_series(history, "mdot_total_kg_s", 0.0),
        mdot_ox_kg_s_time=_series(history, "mdot_ox_kg_s", 0.0),
        mdot_f_kg_s_time=_series(history, "mdot_f_kg_s", 0.0),
        of_time=_series(history, "of_ratio", 0.0),
        cstar_time=_series(history, "cstar_effective_mps", 1500.0),
        cf_time=_series(history, "cf_actual", 1.4),
        chamber_temp_k_time=_derive_chamber_temperature_history_k(
            history=history,
            geometry=geometry,
            thermal_config=thermal_config,
        ),
        gamma_time=_series(history, "gamma_e", 1.2),
        throat_area_m2=float(geometry.throat_area_m2),
        area_ratio=float(geometry.nozzle_area_ratio),
        burn_time_s=float(time_s[-1] - time_s[0]) if len(time_s) > 1 else 0.0,
        ambient_pressure_pa=float(ambient_pressure_pa),
        time_s=time_s,
        notes=[note],
    )


def _user_override_case(
    thermal_config: Mapping[str, Any],
    geometry: GeometryDefinition,
) -> ThermalLoadCase:
    override = dict(thermal_config.get("user_override_load_case", {}))
    burn_time_s = float(override.get("burn_time_s", 1.0))
    time_step_s = float(override.get("time_step_s", 0.05))
    step_count = max(int(math.ceil(burn_time_s / max(time_step_s, 1.0e-6))), 2)
    time_s = [index * burn_time_s / float(step_count - 1) for index in range(step_count)]

    def _constant_series(key: str, default: float) -> list[float]:
        return [float(override.get(key, default))] * len(time_s)

    return ThermalLoadCase(
        case_name=str(override.get("case_name", "user_override")),
        source_stage=str(override.get("source_stage", "user_override")),
        time_series_reference="user_override",
        chamber_pressure_pa_time=_constant_series("chamber_pressure_pa", 0.0),
        mdot_total_kg_s_time=_constant_series("mdot_total_kg_s", 0.0),
        mdot_ox_kg_s_time=_constant_series("mdot_ox_kg_s", 0.0),
        mdot_f_kg_s_time=_constant_series("mdot_f_kg_s", 0.0),
        of_time=_constant_series("of_ratio", 6.0),
        cstar_time=_constant_series("cstar_mps", 1500.0),
        cf_time=_constant_series("cf_actual", 1.4),
        chamber_temp_k_time=_constant_series("chamber_temp_k", float(thermal_config.get("reference_chamber_temp_k", 3200.0))),
        gamma_time=_constant_series("gamma", 1.2),
        throat_area_m2=float(geometry.throat_area_m2),
        area_ratio=float(geometry.nozzle_area_ratio),
        burn_time_s=burn_time_s,
        ambient_pressure_pa=float(override.get("ambient_pressure_pa", 101325.0)),
        time_s=time_s,
        notes=[str(item) for item in override.get("notes", [])],
    )


def _peak_thermal_driver(case: ThermalLoadCase) -> float:
    return max(
        (
            max(pc_pa, 0.0) ** 0.8
            * max(cstar_mps, 1.0) ** -0.2
            * max(temp_k, 1.0)
        )
        for pc_pa, cstar_mps, temp_k in zip(case.chamber_pressure_pa_time, case.cstar_time, case.chamber_temp_k_time)
    )


def build_thermal_load_cases(
    thermal_config: Mapping[str, Any],
    geometry: GeometryDefinition,
    *,
    nominal_payload: Mapping[str, Any],
    corner_payload: Mapping[str, Any] | None = None,
    ballistics_payload: Mapping[str, Any] | None = None,
) -> tuple[list[ThermalLoadCase], list[str]]:
    """Build explicit transient thermal load cases from available solver outputs."""

    settings = dict(thermal_config)
    warnings: list[str] = []
    ambient_pressure_pa = float(
        settings.get("user_override_load_case", {}).get(
            "ambient_pressure_pa",
            nominal_payload["result"]["runtime"]["simulation"].ambient_pressure_pa,
        )
    )
    load_cases: list[ThermalLoadCase] = []
    nominal_history = nominal_payload["result"]["history"]

    if settings.get("include_nominal_initial_case", True) or settings["load_source"] == "nominal_0d":
        load_cases.append(
            _load_case_from_history(
                case_name="nominal_transient_0d",
                source_stage="nominal_0d",
                history=nominal_history,
                geometry=geometry,
                thermal_config=settings,
                ambient_pressure_pa=ambient_pressure_pa,
                note="Nominal transient 0D history.",
            )
        )

    if corner_payload is not None and settings.get("include_corner_case_envelope", True):
        candidate_cases: list[ThermalLoadCase] = []
        for item in corner_payload.get("corners", []):
            history = item["result"]["history"]
            if not history:
                continue
            candidate_cases.append(
                _load_case_from_history(
                    case_name=f"{item['case_name']}_transient_0d",
                    source_stage="corner_case_envelope",
                    history=history,
                    geometry=geometry,
                    thermal_config=settings,
                    ambient_pressure_pa=ambient_pressure_pa,
                    note=f"Transient corner-case history: {item['case_name']}.",
                )
            )
        if candidate_cases:
            load_cases.append(max(candidate_cases, key=_peak_thermal_driver))
        else:
            warnings.append("Corner-case thermal envelope requested, but no converged corner-case histories were available.")

    if ballistics_payload is not None and settings.get("include_internal_ballistics_case", True):
        history = ballistics_payload["result"]["history"]
        if history:
            load_cases.append(
                _load_case_from_history(
                    case_name="transient_1d",
                    source_stage="transient_1d",
                    history=history,
                    geometry=geometry,
                    thermal_config=settings,
                    ambient_pressure_pa=ambient_pressure_pa,
                    note="Transient quasi-1D history.",
                )
            )
        else:
            warnings.append("Transient 1D thermal load source requested, but the internal-ballistics history was empty.")

    if settings["load_source"] == "user_override":
        load_cases.append(_user_override_case(settings, geometry))

    if not load_cases:
        raise RuntimeError("No thermal load cases were generated from the available workflow outputs.")
    return load_cases, warnings
