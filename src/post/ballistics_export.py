"""Export helpers for quasi-1D internal ballistics outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np

from src.analysis.summaries import constraint_rows
from src.io_utils import write_json
from src.post.csv_export import write_mapping_csv, write_rows_csv
from src.sizing.geometry_types import GeometryDefinition


def _history_rows(history: Mapping[str, Any]) -> list[dict[str, Any]]:
    time_s = np.asarray(history.get("t_s", []), dtype=float)
    if time_s.size == 0:
        return []
    keys = [key for key, value in history.items() if isinstance(value, np.ndarray) and value.shape == time_s.shape]
    return [{key: float(history[key][index]) for key in keys} for index in range(len(time_s))]


def _axial_rows(axial_history: Mapping[str, Any]) -> list[dict[str, Any]]:
    time_s = np.asarray(axial_history.get("time_s", []), dtype=float)
    x_m = np.asarray(axial_history.get("x_m", []), dtype=float)
    cell_length_m = np.asarray(axial_history.get("cell_length_m", []), dtype=float)
    if time_s.size == 0 or x_m.size == 0:
        return []

    field_names = [
        "port_radius_m",
        "port_area_m2",
        "wetted_perimeter_m",
        "oxidizer_mass_flow_kg_s",
        "oxidizer_flux_kg_m2_s",
        "effective_regression_flux_kg_m2_s",
        "regression_rate_m_s",
        "fuel_addition_rate_kg_s",
        "fuel_addition_rate_kg_s_m",
        "cumulative_fuel_mass_flow_kg_s",
        "total_mass_flow_kg_s",
        "local_of_ratio",
    ]
    rows: list[dict[str, Any]] = []
    for time_index, current_time_s in enumerate(time_s):
        for cell_index, x_value_m in enumerate(x_m):
            row = {
                "time_s": float(current_time_s),
                "cell_index": int(cell_index),
                "x_m": float(x_value_m),
                "cell_length_m": float(cell_length_m[cell_index]) if cell_length_m.size else float("nan"),
            }
            for field_name in field_names:
                row[field_name] = float(axial_history[field_name][time_index, cell_index])
            rows.append(row)
    return rows


def _final_axial_profile_rows(axial_history: Mapping[str, Any]) -> list[dict[str, Any]]:
    time_s = np.asarray(axial_history.get("time_s", []), dtype=float)
    x_m = np.asarray(axial_history.get("x_m", []), dtype=float)
    if time_s.size == 0 or x_m.size == 0:
        return []
    final_index = len(time_s) - 1
    rows: list[dict[str, Any]] = []
    for cell_index, x_value_m in enumerate(x_m):
        rows.append(
            {
                "time_s": float(time_s[final_index]),
                "cell_index": int(cell_index),
                "x_m": float(x_value_m),
                "cell_length_m": float(axial_history["cell_length_m"][cell_index]),
                "port_radius_m": float(axial_history["port_radius_m"][final_index, cell_index]),
                "port_radius_mm": float(axial_history["port_radius_mm"][final_index, cell_index]),
                "port_area_m2": float(axial_history["port_area_m2"][final_index, cell_index]),
                "wetted_perimeter_m": float(axial_history["wetted_perimeter_m"][final_index, cell_index]),
                "oxidizer_mass_flow_kg_s": float(axial_history["oxidizer_mass_flow_kg_s"][final_index, cell_index]),
                "oxidizer_flux_kg_m2_s": float(axial_history["oxidizer_flux_kg_m2_s"][final_index, cell_index]),
                "regression_rate_m_s": float(axial_history["regression_rate_m_s"][final_index, cell_index]),
                "regression_rate_mm_s": float(axial_history["regression_rate_mm_s"][final_index, cell_index]),
                "fuel_addition_rate_kg_s": float(axial_history["fuel_addition_rate_kg_s"][final_index, cell_index]),
                "total_mass_flow_kg_s": float(axial_history["total_mass_flow_kg_s"][final_index, cell_index]),
                "local_of_ratio": float(axial_history["local_of_ratio"][final_index, cell_index]),
            }
        )
    return rows


def _summary_lines(
    *,
    geometry: GeometryDefinition,
    metrics: Mapping[str, Any],
    constraints: Mapping[str, Any],
    warnings: list[str],
    comparison: Mapping[str, Any] | None,
) -> list[str]:
    lines = [
        "Internal Ballistics Summary",
        f"Status: {metrics.get('status')}",
        f"Stop reason: {metrics.get('stop_reason')}",
        f"Geometry valid: {metrics.get('geometry_valid')}",
        f"Constraints pass: {constraints.get('all_pass')}",
        f"Burn time achieved: {metrics.get('burn_time_actual_s')}",
        f"Total impulse: {metrics.get('impulse_total_ns')}",
        f"Average thrust: {metrics.get('thrust_avg_n')}",
        f"Peak thrust: {metrics.get('thrust_peak_n')}",
        f"Average Pc: {metrics.get('pc_avg_bar')}",
        f"Average O/F: {metrics.get('of_avg')}",
        f"Head/Mid/Tail final port diameters [mm]: "
        f"{metrics.get('port_diameter_head_final_mm')} / {metrics.get('port_diameter_mid_final_mm')} / {metrics.get('port_diameter_tail_final_mm')}",
        f"Initial L*: {geometry.lstar_initial_m}",
        "",
        "Warnings:",
        *(warnings or ["None"]),
    ]
    if comparison is not None:
        lines.extend(
            [
                "",
                "0D vs 1D Comparison:",
                f"Impulse delta [%]: {comparison.get('impulse_delta_percent')}",
                f"Burn-time delta [%]: {comparison.get('burn_time_delta_percent')}",
                f"Average-thrust delta [%]: {comparison.get('thrust_avg_delta_percent')}",
            ]
        )
    return lines


def write_ballistics_outputs(
    output_dir: str | Path,
    *,
    result: Mapping[str, Any],
    metrics: Mapping[str, Any],
    constraints: Mapping[str, Any],
    geometry: GeometryDefinition,
    comparison: Mapping[str, Any] | None = None,
) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    final_state = result.get("final_state")
    write_rows_csv(destination / "internal_ballistics_history.csv", _history_rows(result.get("history", {})))
    write_rows_csv(destination / "internal_ballistics_axial_history.csv", _axial_rows(result.get("axial_history", {})))
    write_rows_csv(destination / "internal_ballistics_final_axial_profile.csv", _final_axial_profile_rows(result.get("axial_history", {})))
    write_mapping_csv(destination / "internal_ballistics_metrics.csv", metrics)
    write_json(destination / "internal_ballistics_metrics.json", dict(metrics))
    write_rows_csv(destination / "internal_ballistics_constraints.csv", constraint_rows(constraints))
    write_json(destination / "internal_ballistics_constraints.json", dict(constraints))
    write_json(destination / "internal_ballistics_result.json", {
        "status": result.get("status"),
        "stop_reason": result.get("stop_reason"),
        "warnings": list(result.get("warnings", [])),
        "final_state": None
        if final_state is None
        else {
            "time_s": float(final_state.time_s),
            "tank_mass_kg": float(final_state.tank_mass_kg),
            "tank_internal_energy_j": float(final_state.tank_internal_energy_j),
            "port_radii_m": [float(value) for value in np.asarray(final_state.port_radii_m, dtype=float)],
        },
    })
    if comparison is not None:
        write_rows_csv(destination / "internal_ballistics_vs_0d.csv", comparison.get("rows", []))
        write_json(destination / "internal_ballistics_vs_0d.json", comparison)
    (destination / "internal_ballistics_summary.txt").write_text(
        "\n".join(
            _summary_lines(
                geometry=geometry,
                metrics=metrics,
                constraints=constraints,
                warnings=list(result.get("warnings", [])),
                comparison=comparison,
            )
        )
        + "\n",
        encoding="utf-8",
    )
