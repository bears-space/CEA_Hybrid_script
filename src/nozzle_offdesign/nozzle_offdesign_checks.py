"""Aggregate validity flags and warnings for nozzle off-design results."""

from __future__ import annotations

from src.nozzle_offdesign.nozzle_offdesign_types import NozzleOffDesignResult


def build_validity_flags(result: NozzleOffDesignResult) -> dict[str, bool]:
    """Return named validity flags for the nozzle off-design workflow."""

    return {
        "explicit_governing_case": bool(result.governing_case.case_name),
        "ambient_case_results_present": bool(result.ambient_case_results),
        "transient_results_present": bool(result.transient_results),
        "sea_level_summary_identified": result.sea_level_summary is not None,
        "vacuum_summary_identified": result.vacuum_summary is not None,
        "separation_heuristic_labeled": bool(result.separation_result.model_assumptions),
        "recommendation_identified": bool(result.recommendations.get("recommended_usage_mode")),
    }


def collect_nozzle_offdesign_warnings(result: NozzleOffDesignResult) -> list[str]:
    """Flatten warnings across the nozzle off-design result tree."""

    warnings = list(result.warnings)
    if result.separation_result.separation_warning:
        warnings.append(result.separation_result.separation_warning)
    warnings.extend(str(item) for item in result.recommendations.get("notes", []))
    deduped: list[str] = []
    for warning in warnings:
        if warning not in deduped:
            deduped.append(warning)
    return deduped
