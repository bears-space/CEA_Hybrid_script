"""Structural output export, reports, and lightweight plots."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from src.io_utils import write_json
from src.post.csv_export import write_rows_csv
from src.post.plotting import write_grouped_horizontal_bar_chart, write_horizontal_bar_chart
from src.structural.structural_types import StructuralLoadCase, StructuralSizingResult


def _component_rows(result: StructuralSizingResult) -> list[dict[str, float | str | bool | None]]:
    return [
        {
            "component": "chamber_wall",
            "required_thickness_mm": result.chamber_wall_result.required_thickness_m * 1000.0,
            "selected_thickness_mm": result.chamber_wall_result.selected_thickness_m * 1000.0,
            "margin_to_allowable": result.chamber_wall_result.margin_to_allowable,
            "valid": result.chamber_wall_result.valid,
        },
        {
            "component": "forward_closure",
            "required_thickness_mm": result.forward_closure_result.required_thickness_m * 1000.0,
            "selected_thickness_mm": result.forward_closure_result.selected_thickness_m * 1000.0,
            "margin_to_allowable": result.forward_closure_result.margin_to_allowable,
            "valid": result.forward_closure_result.valid,
        },
        {
            "component": "aft_closure",
            "required_thickness_mm": result.aft_closure_result.required_thickness_m * 1000.0,
            "selected_thickness_mm": result.aft_closure_result.selected_thickness_m * 1000.0,
            "margin_to_allowable": result.aft_closure_result.margin_to_allowable,
            "valid": result.aft_closure_result.valid,
        },
        {
            "component": "injector_plate",
            "required_thickness_mm": result.injector_plate_result.required_thickness_m * 1000.0,
            "selected_thickness_mm": result.injector_plate_result.selected_thickness_m * 1000.0,
            "margin_to_allowable": result.injector_plate_result.margin_to_allowable,
            "valid": result.injector_plate_result.valid,
        },
        {
            "component": "nozzle_mount",
            "required_thickness_mm": result.nozzle_mount_result.required_thickness_m * 1000.0,
            "selected_thickness_mm": result.nozzle_mount_result.selected_thickness_m * 1000.0,
            "margin_to_allowable": result.nozzle_mount_result.margin_to_allowable,
            "valid": result.nozzle_mount_result.valid,
        },
    ]


def _summary_lines(load_cases: Sequence[StructuralLoadCase], result: StructuralSizingResult) -> list[str]:
    warnings = result.warnings or ["None"]
    canonical_state = dict(result.canonical_state or {})
    canonical_materials = dict(canonical_state.get("materials", {}))
    canonical_geometry = dict(canonical_state.get("geometry", {}))
    fastener_line = (
        "Not applicable"
        if result.fastener_result.fastener_count == 0
        else (
            f"{result.fastener_result.fastener_count} x {result.fastener_result.nominal_diameter_m * 1000.0:.2f} mm, "
            f"required count {result.fastener_result.required_fastener_count}"
        )
    )
    governing_margin = min(value for value in result.summary_margins.values() if value is not None)
    return [
        "Structural Sizing Summary",
        f"Governing load case: {result.governing_load_case.case_name} ({result.governing_load_case.source_stage})",
        f"Load cases considered: {len(load_cases)}",
        f"Chamber material: {canonical_materials.get('shell_material', result.chamber_wall_result.material_name)}",
        f"Injector hole count: {canonical_geometry.get('injector_hole_count', result.injector_plate_result.hole_count)}",
        f"Chamber required thickness [mm]: {result.chamber_wall_result.required_thickness_m * 1000.0:.3f}",
        f"Chamber selected thickness [mm]: {result.chamber_wall_result.selected_thickness_m * 1000.0:.3f}",
        f"Forward closure required thickness [mm]: {result.forward_closure_result.required_thickness_m * 1000.0:.3f}",
        f"Aft closure required thickness [mm]: {result.aft_closure_result.required_thickness_m * 1000.0:.3f}",
        f"Injector plate valid: {result.injector_plate_result.valid}",
        f"Closure separating force [N]: {result.governing_load_case.closure_separating_force_n:.2f}",
        f"Fastener summary: {fastener_line}",
        f"Estimated structural mass [kg]: {result.total_structural_mass_estimate_kg:.3f}",
        f"Governing margin: {governing_margin:.3f}",
        f"Structural valid: {result.structural_valid}",
        "",
        "Warnings:",
        *warnings,
    ]


def write_structural_outputs(
    output_dir: str | Path,
    *,
    load_cases: Sequence[StructuralLoadCase],
    result: StructuralSizingResult,
) -> Path:
    """Write the standard structural output bundle."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    load_case_rows = [load_case.to_dict() for load_case in load_cases]
    component_rows = _component_rows(result)
    write_json(destination / "structural_load_cases.json", {"load_cases": load_case_rows})
    write_json(destination / "structural_sizing.json", result.to_dict())
    write_rows_csv(destination / "structural_sizing.csv", component_rows)
    write_rows_csv(
        destination / "structural_mass_breakdown.csv",
        [{"component": key, "mass_kg": value} for key, value in result.mass_breakdown_kg.items()],
    )
    write_json(
        destination / "structural_checks.json",
        {
            "validity_flags": result.validity_flags,
            "summary_margins": result.summary_margins,
            "structural_valid": result.structural_valid,
            "warnings": result.warnings,
            "failure_reason": result.failure_reason,
        },
    )
    (destination / "structural_summary.txt").write_text("\n".join(_summary_lines(load_cases, result)) + "\n", encoding="utf-8")

    write_grouped_horizontal_bar_chart(
        destination / "thickness_required_vs_selected.svg",
        [
            {
                "label": row["component"],
                "values": {
                    "Required [mm]": row["required_thickness_mm"],
                    "Selected [mm]": row["selected_thickness_mm"],
                },
            }
            for row in component_rows
        ],
        ["Required [mm]", "Selected [mm]"],
        "Structural Thickness Comparison",
        "Thickness [mm]",
    )
    write_horizontal_bar_chart(
        destination / "margin_by_component.svg",
        [{"label": row["component"], "value": row["margin_to_allowable"] or 0.0} for row in component_rows],
        "Structural Margin by Component",
        "Margin to allowable [-]",
    )
    write_horizontal_bar_chart(
        destination / "structural_mass_breakdown.svg",
        [{"label": key, "value": value} for key, value in result.mass_breakdown_kg.items()],
        "Structural Mass Breakdown",
        "Mass [kg]",
    )
    write_grouped_horizontal_bar_chart(
        destination / "load_case_comparison.svg",
        [
            {
                "label": load_case.case_name,
                "values": {
                    "Pc [bar]": load_case.chamber_pressure_pa / 1.0e5,
                    "Closure force [kN]": load_case.closure_separating_force_n / 1000.0,
                },
            }
            for load_case in load_cases
        ],
        ["Pc [bar]", "Closure force [kN]"],
        "Structural Load-Case Comparison",
        "Load metric",
    )
    return destination
