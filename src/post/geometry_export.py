"""Geometry export helpers for the Step 2 freeze workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.io_utils import write_json
from src.post.csv_export import write_rows_csv
from src.sizing.geometry_types import GeometryDefinition


def _flatten_geometry_for_csv(geometry: GeometryDefinition) -> list[dict[str, Any]]:
    payload = geometry.to_dict()
    rows: list[dict[str, Any]] = []
    for key, value in payload.items():
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                rows.append({"key": f"{key}.{nested_key}", "value": nested_value})
        elif isinstance(value, list):
            rows.append({"key": key, "value": " | ".join(map(str, value))})
        else:
            rows.append({"key": key, "value": value})
    return rows


def _summary_lines(geometry: GeometryDefinition) -> list[str]:
    return [
        "Baseline Frozen Geometry",
        f"Geometry valid: {geometry.geometry_valid}",
        f"Chamber ID: {geometry.chamber_id_m * 1000.0:.2f} mm",
        f"Injector face diameter: {geometry.injector_face_diameter_m * 1000.0:.2f} mm",
        f"Prechamber length: {geometry.prechamber_length_m * 1000.0:.2f} mm",
        f"Grain length: {geometry.grain_length_m * 1000.0:.2f} mm",
        f"Initial port diameter: {2.0 * geometry.port_radius_initial_m * 1000.0:.2f} mm",
        f"Grain OD: {2.0 * geometry.grain_outer_radius_m * 1000.0:.2f} mm",
        f"Postchamber length: {geometry.postchamber_length_m * 1000.0:.2f} mm",
        f"Throat diameter: {geometry.throat_diameter_m * 1000.0:.2f} mm",
        f"Nozzle exit diameter: {geometry.nozzle_exit_diameter_m * 1000.0:.2f} mm",
        f"Nozzle area ratio: {geometry.nozzle_area_ratio:.3f}",
        f"Total chamber length: {geometry.total_chamber_length_m * 1000.0:.2f} mm",
        f"Initial free volume: {geometry.free_volume_initial_m3 * 1.0e6:.2f} cc",
        f"Initial L*: {geometry.lstar_initial_m:.3f} m",
        f"Nominal constraints pass: {geometry.nominal_constraint_pass}",
        f"Corner cases pass: {geometry.corner_cases_all_pass}",
        "",
        "Warnings:",
        *(geometry.warnings or ["None"]),
        "",
        "Notes:",
        *(geometry.notes or ["None"]),
    ]


def write_geometry_outputs(output_dir: str | Path, geometry: GeometryDefinition) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    write_json(destination / "baseline_geometry.json", geometry.to_dict())
    write_rows_csv(destination / "baseline_geometry.csv", _flatten_geometry_for_csv(geometry))
    (destination / "geometry_summary.txt").write_text("\n".join(_summary_lines(geometry)) + "\n", encoding="utf-8")

