"""Environment summaries and practical nozzle-usage recommendations."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping, Sequence

from src.nozzle_offdesign.ambient_profiles import altitude_from_pressure_pa
from src.nozzle_offdesign.expansion_state import exit_to_ambient_ratio
from src.nozzle_offdesign.nozzle_offdesign_types import (
    AmbientCaseEvaluationResult,
    NozzleEnvironmentSummary,
    NozzleOperatingPoint,
    SeparationRiskResult,
)
from src.structural.structural_types import StructuralSizingResult
from src.thermal.thermal_types import ThermalSizingResult


def build_environment_summary(
    *,
    ambient_case,
    operating_points: Sequence[NozzleOperatingPoint],
    separation_result: SeparationRiskResult,
) -> NozzleEnvironmentSummary:
    """Summarize nozzle behavior for one ambient case."""

    ratios = [
        exit_to_ambient_ratio(point.exit_pressure_pa, point.ambient_pressure_pa)
        for point in operating_points
        if point.ambient_pressure_pa > 0.0
    ]
    valid_ratios = [ratio for ratio in ratios if ratio is not None]
    state_counter = Counter(point.expansion_state for point in operating_points)
    dominant_state = state_counter.most_common(1)[0][0] if state_counter else "unknown"
    environment_type = ambient_case.environment_type
    return NozzleEnvironmentSummary(
        case_name=ambient_case.case_name,
        environment_type=environment_type,
        ambient_pressure_pa=ambient_case.ambient_pressure_pa,
        ambient_temperature_k=ambient_case.ambient_temperature_k,
        altitude_m=ambient_case.altitude_m,
        average_thrust_n=sum(point.thrust_n for point in operating_points) / max(len(operating_points), 1),
        peak_thrust_n=max(point.thrust_n for point in operating_points),
        average_cf_actual=sum(point.cf_actual for point in operating_points) / max(len(operating_points), 1),
        average_isp_s=sum(point.isp_s for point in operating_points) / max(len(operating_points), 1),
        min_exit_to_ambient_ratio=min(valid_ratios) if valid_ratios else None,
        max_exit_to_ambient_ratio=max(valid_ratios) if valid_ratios else None,
        dominant_expansion_state=dominant_state,
        separation_risk_level=separation_result.risk_level,
        ground_test_relevant=environment_type in {"sea_level_static", "ground_test"},
        flight_relevant=environment_type in {"ascent_profile_point", "vacuum", "user_override"},
        notes=list(ambient_case.notes),
    )


def _special_summary(
    summaries: Sequence[NozzleEnvironmentSummary],
    *,
    predicate,
) -> NozzleEnvironmentSummary | None:
    for summary in summaries:
        if predicate(summary):
            return summary
    return None


def matched_altitude_summary(summaries: Sequence[NozzleEnvironmentSummary]) -> NozzleEnvironmentSummary | None:
    """Return the summary closest to matched expansion."""

    candidates = [
        summary
        for summary in summaries
        if summary.min_exit_to_ambient_ratio is not None and summary.max_exit_to_ambient_ratio is not None
    ]
    if not candidates:
        return None

    def closeness(summary: NozzleEnvironmentSummary) -> float:
        midpoint = 0.5 * (float(summary.min_exit_to_ambient_ratio) + float(summary.max_exit_to_ambient_ratio))
        return abs(midpoint - 1.0)

    return min(candidates, key=closeness)


def build_nozzle_recommendations(
    *,
    evaluations: Sequence[AmbientCaseEvaluationResult],
    structural_result: StructuralSizingResult | None,
    thermal_result: ThermalSizingResult | None,
    nozzle_offdesign_config: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a practical recommendation set for ground test versus flight use."""

    summaries = [evaluation.summary for evaluation in evaluations]
    sea_level = _special_summary(
        summaries,
        predicate=lambda summary: summary.environment_type in {"sea_level_static", "ground_test"},
    )
    vacuum = _special_summary(
        summaries,
        predicate=lambda summary: summary.environment_type == "vacuum" or summary.ambient_pressure_pa <= 1.0,
    )
    matched = matched_altitude_summary(summaries)

    if sea_level is None and summaries:
        sea_level = min(summaries, key=lambda summary: summary.ambient_pressure_pa)
    if vacuum is None and summaries:
        vacuum = min(summaries, key=lambda summary: summary.ambient_pressure_pa)

    ground_cases = [summary for summary in summaries if summary.ground_test_relevant]
    flight_cases = [summary for summary in summaries if summary.flight_relevant]
    ground_penalty_fraction = 0.0
    if sea_level is not None and vacuum is not None and vacuum.average_thrust_n > 0.0:
        ground_penalty_fraction = max(1.0 - (sea_level.average_thrust_n / vacuum.average_thrust_n), 0.0)

    ground_test_suitable = bool(ground_cases) and all(
        summary.separation_risk_level != "high" for summary in ground_cases
    ) and ground_penalty_fraction <= float(nozzle_offdesign_config["recommendations"]["ground_test_penalty_fraction_limit"])
    flight_suitable = bool(flight_cases) and any(
        summary.separation_risk_level != "high" or summary.environment_type == "vacuum"
        for summary in flight_cases
    )

    if ground_test_suitable and flight_suitable:
        usage_mode = "acceptable_for_both"
    elif (not ground_test_suitable) and flight_suitable:
        usage_mode = "baseline_flight_nozzle"
    elif ground_test_suitable and (not flight_suitable):
        usage_mode = "baseline_ground_test_nozzle"
    else:
        usage_mode = "unsuitable_without_redesign"

    notes: list[str] = []
    if matched is not None:
        matched_pressure_pa = 0.5 * (
            float(matched.min_exit_to_ambient_ratio or 1.0) + float(matched.max_exit_to_ambient_ratio or 1.0)
        ) * float(matched.ambient_pressure_pa)
        matched_altitude_m = altitude_from_pressure_pa(matched_pressure_pa)
        if matched_altitude_m is not None:
            notes.append(f"Nozzle is closest to matched expansion around {matched_altitude_m:.0f} m in the sampled environment set.")
    if usage_mode == "baseline_flight_nozzle" and bool(nozzle_offdesign_config["recommendations"]["recommend_separate_ground_test_nozzle"]):
        notes.append("A conservative ground-test nozzle variant is recommended because sea-level operation is more restrictive than flight.")
    if ground_penalty_fraction > 0.0:
        notes.append(f"Sea-level thrust penalty relative to vacuum is {ground_penalty_fraction * 100.0:.1f}%.")

    all_points: list[NozzleOperatingPoint] = [
        point
        for evaluation in evaluations
        for point in evaluation.operating_points
    ]
    structural_candidate = None
    if all_points:
        structural_candidate = max(all_points, key=lambda point: point.thrust_n)
    thermal_candidate = None
    if all_points:
        thermal_candidate = max(all_points, key=lambda point: point.chamber_pressure_pa)

    if structural_result is not None and structural_result.nozzle_mount_result.margin_to_allowable < float(
        nozzle_offdesign_config["recommendations"]["structural_margin_warning_threshold"]
    ):
        notes.append("Nozzle-mount structural margin is already low relative to the off-design thrust envelope.")
    if thermal_result is not None and thermal_result.throat_result.region.thermal_margin_k < float(
        nozzle_offdesign_config["recommendations"]["thermal_margin_warning_k"]
    ):
        notes.append("Throat thermal margin is already low relative to the off-design operating envelope.")

    return {
        "ground_test_suitable": ground_test_suitable,
        "flight_suitable": flight_suitable,
        "recommended_usage_mode": usage_mode,
        "ground_test_penalty_fraction": ground_penalty_fraction,
        "sea_level_case_name": None if sea_level is None else sea_level.case_name,
        "vacuum_case_name": None if vacuum is None else vacuum.case_name,
        "matched_case_name": None if matched is None else matched.case_name,
        "structural_candidate": (
            None
            if structural_candidate is None
            else {
                "operating_point_label": structural_candidate.operating_point_label,
                "time_s": structural_candidate.time_s,
                "thrust_n": structural_candidate.thrust_n,
            }
        ),
        "thermal_candidate": (
            None
            if thermal_candidate is None
            else {
                "operating_point_label": thermal_candidate.operating_point_label,
                "time_s": thermal_candidate.time_s,
                "chamber_pressure_pa": thermal_candidate.chamber_pressure_pa,
            }
        ),
        "notes": notes,
    }


def aggregate_separation_result(results: Iterable[SeparationRiskResult]) -> SeparationRiskResult:
    """Return the governing separation result across environment cases."""

    ordered = {"unknown": -1, "low": 0, "moderate": 1, "high": 2}
    result_list = list(results)
    if not result_list:
        return SeparationRiskResult(
            risk_level="unknown",
            margin_metric=0.0,
            likely_overexpanded=False,
            likely_underexpanded=False,
            startup_risk_flag=False,
            shutdown_risk_flag=False,
            separation_warning="No separation-risk results were available.",
            model_assumptions=["Pressure-ratio separation heuristic only."],
        )
    return max(result_list, key=lambda result: (ordered.get(result.risk_level, -1), -result.margin_metric))
