"""High-level nozzle off-design workflow orchestration."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from src.io_utils import deep_merge
from src.nozzle_offdesign.environment_cases import build_environment_cases
from src.nozzle_offdesign.nozzle_offdesign_checks import build_validity_flags, collect_nozzle_offdesign_warnings
from src.nozzle_offdesign.nozzle_offdesign_export import write_nozzle_offdesign_outputs
from src.nozzle_offdesign.nozzle_offdesign_types import AmbientCaseEvaluationResult, NozzleOffDesignResult, SeparationRiskResult
from src.nozzle_offdesign.nozzle_recommendations import (
    aggregate_separation_result,
    build_environment_summary,
    build_nozzle_recommendations,
    matched_altitude_summary,
)
from src.nozzle_offdesign.separation_checks import evaluate_separation_risk
from src.nozzle_offdesign.transient_nozzle_eval import evaluate_transient_nozzle_case
from src.sizing.geometry_types import GeometryDefinition
from src.structural.structural_types import StructuralSizingResult
from src.thermal.thermal_types import ThermalSizingResult


def merge_nozzle_offdesign_config(
    study_config: Mapping[str, Any],
    override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the nozzle off-design config section after applying optional overrides."""

    override_section = dict(override or {})
    if "nozzle_offdesign" in override_section and isinstance(override_section["nozzle_offdesign"], Mapping):
        override_section = dict(override_section["nozzle_offdesign"])
    return deep_merge(dict(study_config.get("nozzle_offdesign", {})), override_section)


def _build_user_override_history(
    nozzle_offdesign_config: Mapping[str, Any],
) -> dict[str, Any]:
    override = dict(nozzle_offdesign_config.get("user_override_source", {}))
    burn_time_s = float(override.get("burn_time_s", 1.0))
    time_step_s = float(override.get("time_step_s", 0.05))
    step_count = max(int(np.ceil(burn_time_s / max(time_step_s, 1.0e-9))), 2)
    time_s = np.linspace(0.0, burn_time_s, step_count)

    def _series(key: str, default: float) -> np.ndarray:
        return np.full(step_count, float(override.get(key, default)), dtype=float)

    return {
        "t_s": time_s,
        "pc_pa": _series("chamber_pressure_pa", 2.0e6),
        "mdot_total_kg_s": _series("mdot_total_kg_s", 1.5),
        "cf_vac": _series("cf_vac", 1.5),
        "cstar_effective_mps": _series("cstar_mps", 1500.0),
        "gamma_e": _series("gamma_e", 1.2),
        "molecular_weight_exit": _series("molecular_weight_exit", 24.0),
        "exit_pressure_bar": _series("exit_pressure_bar", 0.4e6) / 1.0e5,
    }


def _select_source_history(
    nozzle_offdesign_config: Mapping[str, Any],
    *,
    nominal_payload: Mapping[str, Any],
    corner_payload: Mapping[str, Any] | None = None,
    ballistics_payload: Mapping[str, Any] | None = None,
) -> tuple[str, str, Mapping[str, Any], list[str]]:
    """Select the source engine history for nozzle off-design evaluation."""

    warnings: list[str] = []
    source_mode = str(nozzle_offdesign_config.get("source_mode", "nominal_0d")).lower()
    if source_mode == "user_override":
        return "user_override", "user_override", _build_user_override_history(nozzle_offdesign_config), warnings
    if source_mode == "transient_1d":
        if ballistics_payload is None or not ballistics_payload["result"]["history"]:
            warnings.append("Transient 1D source requested, but the internal-ballistics history was unavailable; falling back to nominal 0D.")
        else:
            return "transient_1d", "transient_1d", ballistics_payload["result"]["history"], warnings
    if source_mode == "corner_case_envelope":
        if corner_payload is None:
            warnings.append("Corner-case envelope source requested, but no corner payload was available; falling back to nominal 0D.")
        else:
            candidate = None
            candidate_pressure = -np.inf
            for item in corner_payload.get("corners", []):
                history = item["result"]["history"]
                if not history:
                    continue
                peak_pressure = float(np.max(np.asarray(history.get("pc_pa", []), dtype=float)))
                if peak_pressure > candidate_pressure:
                    candidate_pressure = peak_pressure
                    candidate = item
            if candidate is not None:
                return candidate["case_name"], "corner_case_envelope", candidate["result"]["history"], warnings
            warnings.append("Corner-case envelope source requested, but no converged corner history was available; falling back to nominal 0D.")
    return "nominal_0d", "nominal_0d", nominal_payload["result"]["history"], warnings


def _governing_case(evaluations: list[AmbientCaseEvaluationResult]) -> tuple[Any, SeparationRiskResult]:
    ordered = {"unknown": -1, "low": 0, "moderate": 1, "high": 2}
    governing = max(
        evaluations,
        key=lambda evaluation: (
            ordered.get(evaluation.separation_result.risk_level, -1),
            -evaluation.separation_result.margin_metric,
            evaluation.summary.peak_thrust_n,
        ),
    )
    return governing.offdesign_case, governing.separation_result


def run_nozzle_offdesign_workflow(
    study_config: Mapping[str, Any],
    nozzle_offdesign_config: Mapping[str, Any],
    output_dir: str,
    *,
    geometry: GeometryDefinition,
    nominal_payload: Mapping[str, Any],
    structural_result: StructuralSizingResult | None = None,
    thermal_result: ThermalSizingResult | None = None,
    corner_payload: Mapping[str, Any] | None = None,
    ballistics_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run first-pass nozzle off-design evaluation and export the standard bundle."""

    environment_cases = build_environment_cases(nozzle_offdesign_config)
    if not environment_cases:
        raise RuntimeError("No ambient environment cases were configured for nozzle off-design evaluation.")
    engine_reference, source_stage, source_history, warnings = _select_source_history(
        nozzle_offdesign_config,
        nominal_payload=nominal_payload,
        corner_payload=corner_payload,
        ballistics_payload=ballistics_payload,
    )
    evaluations: list[AmbientCaseEvaluationResult] = []
    for ambient_case in environment_cases:
        offdesign_case, operating_points = evaluate_transient_nozzle_case(
            case_name=f"{engine_reference}_{ambient_case.case_name}",
            source_stage=source_stage,
            engine_result_reference=engine_reference,
            history=source_history,
            geometry=geometry,
            ambient_case=ambient_case,
            nozzle_offdesign_config=nozzle_offdesign_config,
        )
        separation_result = evaluate_separation_risk(
            operating_points,
            nozzle_offdesign_config["separation_thresholds"],
        )
        summary = build_environment_summary(
            ambient_case=ambient_case,
            operating_points=operating_points,
            separation_result=separation_result,
        )
        evaluations.append(
            AmbientCaseEvaluationResult(
                ambient_case=ambient_case,
                offdesign_case=offdesign_case,
                operating_points=operating_points,
                summary=summary,
                separation_result=separation_result,
            )
        )

    governing_case, governing_separation = _governing_case(evaluations)
    summaries = [evaluation.summary for evaluation in evaluations]
    sea_level_summary = next(
        (summary for summary in summaries if summary.environment_type in {"sea_level_static", "ground_test"}),
        None,
    )
    vacuum_summary = next(
        (summary for summary in summaries if summary.environment_type == "vacuum" or summary.ambient_pressure_pa <= 1.0),
        None,
    )
    matched_summary = matched_altitude_summary(summaries)
    recommendations = build_nozzle_recommendations(
        evaluations=evaluations,
        structural_result=structural_result,
        thermal_result=thermal_result,
        nozzle_offdesign_config=nozzle_offdesign_config,
    )
    preliminary = NozzleOffDesignResult(
        governing_case=governing_case,
        ambient_case_results=evaluations,
        transient_results={
            evaluation.summary.case_name: [point.to_dict() for point in evaluation.operating_points]
            for evaluation in evaluations
        },
        sea_level_summary=sea_level_summary,
        vacuum_summary=vacuum_summary,
        matched_altitude_summary=matched_summary,
        separation_result=aggregate_separation_result(evaluation.separation_result for evaluation in evaluations),
        recommendations=recommendations,
        validity_flags={},
        nozzle_offdesign_valid=False,
        warnings=warnings,
        failure_reason=None,
        notes=[
            "First-pass nozzle off-design assessment only.",
            "Detailed separated-flow CFD, side-load prediction, and trajectory-derived ambient coupling are later refinements.",
        ],
    )
    validity_flags = build_validity_flags(preliminary)
    final_result = NozzleOffDesignResult(
        governing_case=preliminary.governing_case,
        ambient_case_results=preliminary.ambient_case_results,
        transient_results=preliminary.transient_results,
        sea_level_summary=preliminary.sea_level_summary,
        vacuum_summary=preliminary.vacuum_summary,
        matched_altitude_summary=preliminary.matched_altitude_summary,
        separation_result=governing_separation,
        recommendations=preliminary.recommendations,
        validity_flags=validity_flags,
        nozzle_offdesign_valid=all(validity_flags.values()),
        warnings=collect_nozzle_offdesign_warnings(preliminary),
        failure_reason=None if all(validity_flags.values()) else "One or more nozzle off-design checks failed.",
        notes=preliminary.notes,
    )
    destination = write_nozzle_offdesign_outputs(output_dir, environment_cases=environment_cases, result=final_result)
    return {
        "output_dir": destination,
        "environment_cases": environment_cases,
        "result": final_result,
    }
