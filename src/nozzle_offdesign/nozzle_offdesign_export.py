"""Nozzle off-design output export, reports, and lightweight plots."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from src.io_utils import write_json
from src.nozzle_offdesign.nozzle_offdesign_types import AmbientEnvironmentCase, NozzleOffDesignResult
from src.post.csv_export import write_rows_csv
from src.post.plotting import write_grouped_horizontal_bar_chart, write_line_plot


EXPANSION_STATE_INDEX = {
    "strongly_overexpanded": 1.0,
    "moderately_overexpanded": 2.0,
    "near_matched": 3.0,
    "moderately_underexpanded": 4.0,
    "strongly_underexpanded": 5.0,
}


def _summary_lines(result: NozzleOffDesignResult) -> list[str]:
    warnings = result.warnings or ["None"]
    recommendations = result.recommendations
    sea_level_thrust = None if result.sea_level_summary is None else result.sea_level_summary.average_thrust_n
    vacuum_thrust = None if result.vacuum_summary is None else result.vacuum_summary.average_thrust_n
    return [
        "Nozzle Off-Design Summary",
        f"Governing off-design case: {result.governing_case.case_name} ({result.governing_case.source_stage})",
        f"Sea-level average thrust [N]: {'n/a' if sea_level_thrust is None else f'{sea_level_thrust:.2f}'}",
        f"Vacuum average thrust [N]: {'n/a' if vacuum_thrust is None else f'{vacuum_thrust:.2f}'}",
        f"Sea-level thrust penalty relative to vacuum [%]: {float(recommendations.get('ground_test_penalty_fraction', 0.0)) * 100.0:.1f}",
        f"Overall separation risk: {result.separation_result.risk_level}",
        f"Ground-test suitable: {recommendations.get('ground_test_suitable')}",
        f"Flight suitable: {recommendations.get('flight_suitable')}",
        f"Recommended usage mode: {recommendations.get('recommended_usage_mode')}",
        f"Nozzle off-design valid: {result.nozzle_offdesign_valid}",
        "",
        "Warnings:",
        *warnings,
    ]


def _environment_rows(result: NozzleOffDesignResult) -> list[dict[str, float | str | bool | None]]:
    return [
        {
            "case_name": evaluation.summary.case_name,
            "environment_type": evaluation.summary.environment_type,
            "ambient_pressure_pa": evaluation.summary.ambient_pressure_pa,
            "altitude_m": evaluation.summary.altitude_m,
            "average_thrust_n": evaluation.summary.average_thrust_n,
            "peak_thrust_n": evaluation.summary.peak_thrust_n,
            "average_cf_actual": evaluation.summary.average_cf_actual,
            "average_isp_s": evaluation.summary.average_isp_s,
            "min_exit_to_ambient_ratio": evaluation.summary.min_exit_to_ambient_ratio,
            "max_exit_to_ambient_ratio": evaluation.summary.max_exit_to_ambient_ratio,
            "dominant_expansion_state": evaluation.summary.dominant_expansion_state,
            "separation_risk_level": evaluation.summary.separation_risk_level,
        }
        for evaluation in result.ambient_case_results
    ]


def _transient_rows(result: NozzleOffDesignResult) -> list[dict[str, float | str | None]]:
    rows: list[dict[str, float | str | None]] = []
    for evaluation in result.ambient_case_results:
        for point in evaluation.operating_points:
            rows.append(
                {
                    "case_name": evaluation.summary.case_name,
                    "environment_type": evaluation.summary.environment_type,
                    "operating_point_label": point.operating_point_label,
                    "time_s": point.time_s,
                    "ambient_pressure_pa": point.ambient_pressure_pa,
                    "chamber_pressure_pa": point.chamber_pressure_pa,
                    "exit_pressure_pa": point.exit_pressure_pa,
                    "cf_actual": point.cf_actual,
                    "thrust_n": point.thrust_n,
                    "isp_s": point.isp_s,
                    "expansion_state": point.expansion_state,
                    "exit_mach": point.exit_mach,
                }
            )
    return rows


def write_nozzle_offdesign_outputs(
    output_dir: str | Path,
    *,
    environment_cases: Sequence[AmbientEnvironmentCase],
    result: NozzleOffDesignResult,
) -> Path:
    """Write the standard nozzle off-design output bundle."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    environment_rows = _environment_rows(result)
    transient_rows = _transient_rows(result)
    write_json(destination / "nozzle_environment_cases.json", {"environment_cases": [case.to_dict() for case in environment_cases]})
    write_json(destination / "nozzle_offdesign_results.json", result.to_dict())
    write_json(destination / "nozzle_recommendations.json", result.recommendations)
    write_json(
        destination / "nozzle_checks.json",
        {
            "validity_flags": result.validity_flags,
            "nozzle_offdesign_valid": result.nozzle_offdesign_valid,
            "warnings": result.warnings,
            "failure_reason": result.failure_reason,
        },
    )
    write_rows_csv(destination / "nozzle_operating_points.csv", environment_rows)
    write_rows_csv(destination / "nozzle_transient_offdesign.csv", transient_rows)
    (destination / "nozzle_offdesign_summary.txt").write_text(
        "\n".join(_summary_lines(result)) + "\n",
        encoding="utf-8",
    )

    if environment_rows:
        sorted_rows = sorted(environment_rows, key=lambda row: float(row["ambient_pressure_pa"]))
        ambient_pressure_bar = [float(row["ambient_pressure_pa"]) / 1.0e5 for row in sorted_rows]
        write_line_plot(
            destination / "thrust_vs_ambient_pressure.svg",
            [{"label": "Average thrust [N]", "x": ambient_pressure_bar, "y": [float(row["average_thrust_n"]) for row in sorted_rows]}],
            "Thrust vs Ambient Pressure",
            "Ambient Pressure [bar]",
            "Average Thrust [N]",
        )
        write_line_plot(
            destination / "cf_vs_ambient_pressure.svg",
            [{"label": "Average Cf [-]", "x": ambient_pressure_bar, "y": [float(row["average_cf_actual"]) for row in sorted_rows]}],
            "Cf vs Ambient Pressure",
            "Ambient Pressure [bar]",
            "Average Cf [-]",
        )
        ratio_values = []
        for row in sorted_rows:
            min_ratio = row["min_exit_to_ambient_ratio"]
            max_ratio = row["max_exit_to_ambient_ratio"]
            if min_ratio is None or max_ratio is None:
                ratio_values.append(0.0)
            else:
                ratio_values.append(0.5 * (float(min_ratio) + float(max_ratio)))
        write_line_plot(
            destination / "exit_to_ambient_ratio_vs_ambient_pressure.svg",
            [{"label": "Pe/Pa midpoint [-]", "x": ambient_pressure_bar, "y": ratio_values}],
            "Exit-to-Ambient Pressure Ratio vs Ambient Pressure",
            "Ambient Pressure [bar]",
            "Pe/Pa [-]",
        )

    selected_cases = []
    if result.sea_level_summary is not None:
        selected_cases.append(result.sea_level_summary.case_name)
    if result.vacuum_summary is not None and result.vacuum_summary.case_name not in selected_cases:
        selected_cases.append(result.vacuum_summary.case_name)
    selected_evaluations = [
        evaluation
        for evaluation in result.ambient_case_results
        if evaluation.summary.case_name in selected_cases
    ]
    if selected_evaluations:
        write_line_plot(
            destination / "transient_thrust_selected_cases.svg",
            [
                {
                    "label": f"{evaluation.summary.case_name} thrust [N]",
                    "x": [0.0 if point.time_s is None else point.time_s for point in evaluation.operating_points],
                    "y": [point.thrust_n for point in evaluation.operating_points],
                }
                for evaluation in selected_evaluations
            ],
            "Transient Thrust for Selected Ambient Cases",
            "Time [s]",
            "Thrust [N]",
        )
        write_line_plot(
            destination / "expansion_state_over_burn.svg",
            [
                {
                    "label": f"{evaluation.summary.case_name} state index",
                    "x": [0.0 if point.time_s is None else point.time_s for point in evaluation.operating_points],
                    "y": [EXPANSION_STATE_INDEX.get(point.expansion_state, 0.0) for point in evaluation.operating_points],
                }
                for evaluation in selected_evaluations
            ],
            "Expansion State Over Burn (1=strong overexpanded, 5=strong underexpanded)",
            "Time [s]",
            "State Index [-]",
        )

    write_grouped_horizontal_bar_chart(
        destination / "environment_thrust_comparison.svg",
        [
            {
                "label": row["case_name"],
                "values": {
                    "Average thrust [N]": row["average_thrust_n"],
                    "Peak thrust [N]": row["peak_thrust_n"],
                },
            }
            for row in environment_rows
        ],
        ["Average thrust [N]", "Peak thrust [N]"],
        "Nozzle Environment Comparison",
        "Value",
    )
    return destination
