"""Transient nozzle off-design evaluation over existing solver histories."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

from src.sizing.geometry_types import GeometryDefinition
from src.nozzle_offdesign.nozzle_offdesign_types import AmbientEnvironmentCase, NozzleOffDesignCase, NozzleOperatingPoint
from src.nozzle_offdesign.nozzle_performance import derive_exit_pressure_ratio, evaluate_offdesign_operating_point
from src.nozzle_offdesign.separation_checks import separation_cf_penalty_multiplier


def _derived_chamber_temperature_k(
    *,
    geometry: GeometryDefinition,
    cstar_mps: float,
    nozzle_offdesign_config: Mapping[str, Any],
) -> float | None:
    reference = geometry.cea_reference or {}
    reference_temp_k = reference.get("chamber_temperature_k", nozzle_offdesign_config.get("reference_chamber_temp_k"))
    reference_cstar_mps = reference.get("cstar_mps", 1500.0)
    if reference_temp_k is None:
        return None
    exponent = float(nozzle_offdesign_config.get("temperature_scale_exponent", 0.15))
    return float(reference_temp_k) * max(float(cstar_mps) / max(float(reference_cstar_mps), 1.0e-9), 0.5) ** exponent


def select_time_indices(
    history: Mapping[str, Any],
    nozzle_offdesign_config: Mapping[str, Any],
    *,
    use_transient_time_history: bool,
) -> list[int]:
    """Return the history indices to evaluate for a nozzle off-design case."""

    time_s = np.asarray(history.get("t_s", []), dtype=float)
    if time_s.size == 0:
        raise ValueError("No history is available for nozzle off-design evaluation.")
    if not use_transient_time_history:
        operating_point_mode = str(nozzle_offdesign_config.get("steady_point_mode", "peak_pc")).lower()
        if operating_point_mode == "initial":
            return [0]
        if operating_point_mode == "final":
            return [len(time_s) - 1]
        return [int(np.argmax(np.asarray(history["pc_pa"], dtype=float)))]

    manual_indices = nozzle_offdesign_config.get("selected_time_indices")
    if manual_indices:
        return sorted(
            {
                min(max(int(index), 0), len(time_s) - 1)
                for index in manual_indices
            }
        )

    sample_count = int(nozzle_offdesign_config.get("transient_sample_count", min(len(time_s), 25)))
    indices = set(int(index) for index in np.linspace(0, len(time_s) - 1, max(sample_count, 2), dtype=int))
    indices.add(0)
    indices.add(len(time_s) - 1)
    indices.add(int(np.argmax(np.asarray(history["pc_pa"], dtype=float))))
    return sorted(indices)


def evaluate_transient_nozzle_case(
    *,
    case_name: str,
    source_stage: str,
    engine_result_reference: str,
    history: Mapping[str, Any],
    geometry: GeometryDefinition,
    ambient_case: AmbientEnvironmentCase,
    nozzle_offdesign_config: Mapping[str, Any],
) -> tuple[NozzleOffDesignCase, list[NozzleOperatingPoint]]:
    """Evaluate a nozzle history against one ambient environment case."""

    use_transient = bool(nozzle_offdesign_config.get("use_transient_time_history", True))
    selected_indices = select_time_indices(
        history,
        nozzle_offdesign_config,
        use_transient_time_history=use_transient,
    )
    thresholds = dict(nozzle_offdesign_config["expansion_thresholds"])
    separation_thresholds = dict(nozzle_offdesign_config["separation_thresholds"])
    penalties = dict(nozzle_offdesign_config.get("penalties", {}))
    operating_points: list[NozzleOperatingPoint] = []
    pc_history = np.asarray(history["pc_pa"], dtype=float)
    time_history = np.asarray(history.get("t_s", []), dtype=float)
    cf_vac_history = np.asarray(history.get("cf_vac", []), dtype=float)
    cstar_history = np.asarray(history.get("cstar_effective_mps", []), dtype=float)
    gamma_history = np.asarray(history.get("gamma_e", []), dtype=float)
    molecular_weight_history = np.asarray(history.get("molecular_weight_exit", []), dtype=float)
    mdot_history = np.asarray(history.get("mdot_total_kg_s", []), dtype=float)
    exit_pressure_history = np.asarray(history.get("exit_pressure_bar", []), dtype=float) * 1.0e5
    for index in selected_indices:
        operating_label = f"{case_name}_idx_{index}"
        chamber_pressure_pa = float(pc_history[index])
        exit_pressure_ratio = derive_exit_pressure_ratio(
            chamber_pressure_pa=chamber_pressure_pa,
            exit_pressure_pa=float(exit_pressure_history[index]) if exit_pressure_history.size else None,
            fallback_ratio=float(nozzle_offdesign_config.get("fallback_exit_pressure_ratio"))
            if nozzle_offdesign_config.get("fallback_exit_pressure_ratio") is not None
            else None,
        )
        base_point = evaluate_offdesign_operating_point(
            operating_point_label=operating_label,
            time_s=float(time_history[index]) if time_history.size else None,
            chamber_pressure_pa=chamber_pressure_pa,
            chamber_temp_k=_derived_chamber_temperature_k(
                geometry=geometry,
                cstar_mps=float(cstar_history[index]),
                nozzle_offdesign_config=nozzle_offdesign_config,
            ),
            gamma=float(gamma_history[index]) if gamma_history.size else None,
            molecular_weight=float(molecular_weight_history[index]) if molecular_weight_history.size else None,
            total_mass_flow_kg_s=float(mdot_history[index]),
            throat_area_m2=float(geometry.throat_area_m2),
            exit_area_m2=float(geometry.nozzle_exit_area_m2),
            ambient_pressure_pa=float(ambient_case.ambient_pressure_pa),
            cf_vac=float(cf_vac_history[index]),
            cstar_mps=float(cstar_history[index]),
            exit_pressure_ratio=exit_pressure_ratio,
            expansion_thresholds=thresholds,
        )
        penalty_multiplier = 1.0
        if bool(penalties.get("apply_separation_cf_penalty", False)):
            penalty_multiplier = separation_cf_penalty_multiplier(base_point, separation_thresholds, penalties)
        notes = list(base_point.notes)
        if penalty_multiplier < 1.0:
            notes.append(f"Applied conservative off-design Cf penalty multiplier {penalty_multiplier:.3f}.")
        operating_points.append(
            evaluate_offdesign_operating_point(
                operating_point_label=operating_label,
                time_s=base_point.time_s,
                chamber_pressure_pa=base_point.chamber_pressure_pa,
                chamber_temp_k=base_point.chamber_temp_k,
                gamma=base_point.gamma,
                molecular_weight=base_point.molecular_weight,
                total_mass_flow_kg_s=base_point.total_mass_flow_kg_s,
                throat_area_m2=base_point.throat_area_m2,
                exit_area_m2=base_point.exit_area_m2,
                ambient_pressure_pa=base_point.ambient_pressure_pa,
                cf_vac=float(cf_vac_history[index]),
                cstar_mps=float(cstar_history[index]),
                exit_pressure_ratio=exit_pressure_ratio,
                expansion_thresholds=thresholds,
                cf_penalty_multiplier=penalty_multiplier,
                notes=notes,
            )
        )

    offdesign_case = NozzleOffDesignCase(
        case_name=case_name,
        source_stage=source_stage,
        engine_result_reference=engine_result_reference,
        ambient_case_reference=ambient_case.case_name,
        use_transient_time_history=use_transient,
        selected_time_indices=selected_indices,
        notes=[f"Evaluated against ambient case '{ambient_case.case_name}'."],
    )
    return offdesign_case, operating_points
