"""Geometry export helpers for the baseline-geometry workflow."""

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
    main_output_rows = _main_output_rows(geometry)
    failure_reasons = geometry.failure_reasons or ["None"]
    return [
        "Geometry Main Outputs",
        f"Geometry valid: {geometry.geometry_valid}",
        *[f"{row['label']}: {row['value']}" for row in main_output_rows],
        "",
        "Failure Reasons:",
        *failure_reasons,
        "",
        "Warnings:",
        *(geometry.warnings or ["None"]),
        "",
        "Notes:",
        *(geometry.notes or ["None"]),
    ]


def _metric_mm(value_m: float | None) -> str:
    if value_m is None:
        return "n/a"
    return f"{float(value_m) * 1000.0:.2f} mm"


def _metric_deg(value_deg: float | None) -> str:
    if value_deg is None:
        return "n/a"
    return f"{float(value_deg):.2f} deg"


def _metric_area_mm2(value_m2: float | None) -> str:
    if value_m2 is None:
        return "n/a"
    return f"{float(value_m2) * 1.0e6:.3f} mm^2"


def _metric_seconds(value_s: float | None) -> str:
    if value_s is None:
        return "n/a"
    return f"{float(value_s):.3f} s"


def _metric_newtons(value_n: float | None) -> str:
    if value_n is None:
        return "n/a"
    return f"{float(value_n):.2f} N"


def _metric_isp_seconds(value_s: float | None) -> str:
    if value_s is None:
        return "n/a"
    return f"{float(value_s):.3f} s"


def _main_output_rows(geometry: GeometryDefinition) -> list[dict[str, Any]]:
    engine_state = dict(geometry.engine_state or {})
    shell_material = (
        dict(engine_state.get("materials", {})).get("shell_material", "shell")
        if engine_state
        else "shell"
    )
    return [
        {
            "key": "chamber_inner_diameter_excluding_liner_m",
            "label": f"Chamber diameter inner excluding inner liner ({shell_material} inner diameter)",
            "value": _metric_mm(geometry.chamber_inner_diameter_excluding_liner_m),
        },
        {
            "key": "chamber_outer_diameter_excluding_liner_m",
            "label": f"Chamber diameter outer excluding inner liner ({shell_material} outer diameter)",
            "value": _metric_mm(geometry.chamber_outer_diameter_excluding_liner_m),
        },
        {
            "key": "chamber_inner_diameter_including_liner_m",
            "label": "Chamber diameter inner including inner liner (phenolic-lined hot-gas diameter)",
            "value": _metric_mm(geometry.chamber_inner_diameter_including_liner_m),
        },
        {
            "key": "chamber_outer_diameter_including_liner_m",
            "label": "Chamber diameter outer including inner liner",
            "value": _metric_mm(geometry.chamber_outer_diameter_including_liner_m),
        },
        {
            "key": "fuel_inner_diameter_m",
            "label": "Fuel diameter inner (pre-burn port diameter)",
            "value": _metric_mm(geometry.fuel_inner_diameter_m),
        },
        {
            "key": "fuel_outer_diameter_m",
            "label": "Fuel diameter outer (pre-burn grain outer diameter)",
            "value": _metric_mm(geometry.fuel_outer_diameter_m),
        },
        {
            "key": "throat_diameter_m",
            "label": "Throat diameter",
            "value": _metric_mm(geometry.throat_diameter_m),
        },
        {
            "key": "nozzle_exit_diameter_m",
            "label": "Exit diameter",
            "value": _metric_mm(geometry.nozzle_exit_diameter_m),
        },
        {
            "key": "nozzle_length_m",
            "label": "Nozzle length",
            "value": _metric_mm(geometry.nozzle_length_m),
        },
        {
            "key": "inner_liner_thickness_m",
            "label": "Inner liner thickness (phenolic paper)",
            "value": _metric_mm(geometry.inner_liner_thickness_m),
        },
        {
            "key": "postchamber_length_m",
            "label": "Post Combustion chamber length",
            "value": _metric_mm(geometry.postchamber_length_m),
        },
        {
            "key": "prechamber_length_m",
            "label": "Pre Combustion chamber length",
            "value": _metric_mm(geometry.prechamber_length_m),
        },
        {
            "key": "converging_throat_half_angle_deg",
            "label": "Converging throat section angle (half-angle)",
            "value": _metric_deg(geometry.converging_throat_half_angle_deg),
        },
        {
            "key": "injector_hole_count",
            "label": "Injector hole count",
            "value": "n/a" if geometry.injector_hole_count is None else str(int(geometry.injector_hole_count)),
        },
        {
            "key": "injector_total_hole_area_m2",
            "label": "Injector total hole area (sum of area of all oxidizer holes)",
            "value": _metric_area_mm2(geometry.injector_total_hole_area_m2),
        },
        {
            "key": "nominal_isp_avg_s",
            "label": "Average specific impulse",
            "value": _metric_isp_seconds(geometry.nominal_isp_avg_s),
        },
        {
            "key": "nominal_thrust_avg_n",
            "label": "Average thrust",
            "value": _metric_newtons(geometry.nominal_thrust_avg_n),
        },
        {
            "key": "nominal_burn_time_s",
            "label": "Burn time",
            "value": _metric_seconds(geometry.nominal_burn_time_s),
        },
    ]


def write_geometry_outputs(output_dir: str | Path, geometry: GeometryDefinition) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    write_json(destination / "geometry_definition.json", geometry.to_dict())
    write_rows_csv(destination / "geometry_definition.csv", _flatten_geometry_for_csv(geometry))
    write_json(destination / "geometry_main_outputs.json", {"outputs": _main_output_rows(geometry)})
    write_rows_csv(destination / "geometry_main_outputs.csv", _main_output_rows(geometry))
    (destination / "geometry_summary.txt").write_text("\n".join(_summary_lines(geometry)) + "\n", encoding="utf-8")
