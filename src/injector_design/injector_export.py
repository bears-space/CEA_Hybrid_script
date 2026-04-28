"""Export helpers for showerhead injector synthesis outputs."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable

from src.injector_design.injector_types import (
    InjectorCandidateEvaluation,
    InjectorDesignPoint,
    InjectorEffectiveModel,
    InjectorGeometryDefinition,
)
from src.io_utils import write_json
from src.post.csv_export import write_mapping_csv, write_rows_csv
from src.post.plotting import write_line_plot
from src.sizing.geometry_types import GeometryDefinition


def _flatten_geometry_for_csv(geometry: InjectorGeometryDefinition) -> list[dict[str, Any]]:
    payload = geometry.to_dict()
    rows: list[dict[str, Any]] = []
    for key, value in payload.items():
        if key == "ring_definitions":
            continue
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                rows.append({"key": f"{key}.{nested_key}", "value": nested_value})
        elif isinstance(value, list):
            rows.append({"key": key, "value": " | ".join(map(str, value))})
        else:
            rows.append({"key": key, "value": value})
    return rows


def _ring_rows(geometry: InjectorGeometryDefinition) -> list[dict[str, Any]]:
    return [
        {
            "ring_index": ring.ring_index,
            "ring_radius_mm": ring.ring_radius_m * 1000.0,
            "holes_in_ring": ring.holes_in_ring,
            "angular_offset_deg": ring.angular_offset_deg,
            "circumferential_spacing_mm": ring.circumferential_spacing_m * 1000.0,
        }
        for ring in geometry.ring_definitions
    ]


def _candidate_rows(candidates: Iterable[InjectorCandidateEvaluation]) -> list[dict[str, Any]]:
    return [candidate.to_row() for candidate in candidates]


def _hole_centers(geometry: InjectorGeometryDefinition) -> list[tuple[float, float]]:
    centers: list[tuple[float, float]] = []
    if geometry.center_hole_enabled:
        centers.append((0.0, 0.0))
    for ring in geometry.ring_definitions:
        if ring.holes_in_ring <= 0:
            continue
        angular_step_rad = 2.0 * math.pi / ring.holes_in_ring
        offset_rad = math.radians(ring.angular_offset_deg)
        for index in range(ring.holes_in_ring):
            angle_rad = offset_rad + index * angular_step_rad
            centers.append(
                (
                    ring.ring_radius_m * math.cos(angle_rad),
                    ring.ring_radius_m * math.sin(angle_rad),
                )
            )
    return centers


def _write_pattern_svg(path: Path, geometry: InjectorGeometryDefinition) -> None:
    width = 900
    height = 900
    view_extent_m = max(geometry.plate_outer_diameter_m, geometry.active_face_diameter_m) * 0.6
    scale = 360.0 / max(view_extent_m, 1.0e-9)
    cx = width / 2.0
    cy = height / 2.0
    plate_radius_px = 0.5 * geometry.plate_outer_diameter_m * scale
    active_radius_px = 0.5 * geometry.active_face_diameter_m * scale
    hole_radius_px = 0.5 * geometry.hole_diameter_m * scale

    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{plate_radius_px:.1f}" fill="#f8fafc" stroke="#1f2937" stroke-width="3"/>',
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{active_radius_px:.1f}" fill="none" stroke="#94a3b8" stroke-width="2" stroke-dasharray="10 8"/>',
        f'<text x="{cx:.1f}" y="54" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="26" font-weight="bold" fill="#111827">Axial Showerhead Layout</text>',
        f'<text x="{cx:.1f}" y="86" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="14" fill="#475569">Plate OD {geometry.plate_outer_diameter_m * 1000.0:.2f} mm | Active face {geometry.active_face_diameter_m * 1000.0:.2f} mm | {geometry.hole_count} holes @ {geometry.hole_diameter_m * 1000.0:.3f} mm</text>',
    ]
    for x_m, y_m in _hole_centers(geometry):
        x_px = cx + x_m * scale
        y_px = cy - y_m * scale
        body.append(
            f'<circle cx="{x_px:.2f}" cy="{y_px:.2f}" r="{hole_radius_px:.2f}" fill="#0f766e" stroke="#115e59" stroke-width="1.5"/>'
        )
    body.append("</svg>")
    path.write_text("\n".join(body), encoding="utf-8")


def _summary_lines(
    *,
    engine_geometry: GeometryDefinition,
    design_point: InjectorDesignPoint,
    requirement: dict[str, Any],
    geometry: InjectorGeometryDefinition,
    effective_model: InjectorEffectiveModel,
    candidate_count: int,
) -> list[str]:
    return [
        "Injector Geometry Summary",
        f"Injector type: {geometry.injector_type}",
        f"Design condition source: {design_point.source}",
        f"Geometry valid: {geometry.injector_geometry_valid}",
        f"Plate OD: {geometry.plate_outer_diameter_m * 1000.0:.2f} mm",
        f"Active face diameter: {geometry.active_face_diameter_m * 1000.0:.2f} mm",
        f"Plate thickness: {geometry.plate_thickness_m * 1000.0:.2f} mm",
        f"Selected hole count: {geometry.hole_count}",
        f"Selected hole diameter: {geometry.hole_diameter_m * 1000.0:.3f} mm",
        f"Hole L/D: {geometry.hole_ld_ratio:.3f}",
        f"Ring count: {geometry.ring_count}",
        f"Center hole enabled: {geometry.center_hole_enabled}",
        f"Total geometric area: {geometry.total_geometric_area_m2 * 1.0e6:.3f} mm^2",
        f"Estimated effective CdA: {geometry.estimated_effective_cda_m2 * 1.0e6:.3f} mm^2",
        f"Required effective CdA: {geometry.required_effective_cda_m2 * 1.0e6:.3f} mm^2",
        f"Area ratio to requirement: {geometry.actual_to_required_area_ratio:.4f}",
        f"CdA ratio to requirement: {geometry.actual_to_required_cda_ratio:.4f}",
        f"Estimated design hole velocity: {geometry.design_hole_velocity_m_s:.2f} m/s",
        f"Design injector delta-p: {geometry.design_injector_delta_p_pa / 1.0e5:.3f} bar",
        f"Design injector inlet pressure: {geometry.design_injector_inlet_pressure_pa / 1.0e5:.3f} bar",
        f"Design chamber pressure: {geometry.design_chamber_pressure_pa / 1.0e5:.3f} bar",
        f"Minimum ligament: {geometry.min_ligament_m * 1000.0:.3f} mm",
        f"Minimum active-face edge margin: {geometry.min_edge_margin_m * 1000.0:.3f} mm",
        f"Geometric open-area ratio: {geometry.geometric_open_area_ratio:.4f}",
        f"Plenum depth placeholder: {geometry.plenum_depth_m * 1000.0:.2f} mm",
        f"Plenum volume placeholder: {geometry.plenum_volume_m3 * 1.0e6:.2f} cc",
        f"Face-to-grain distance: {geometry.face_to_grain_distance_m * 1000.0:.2f} mm",
        f"Discharges into prechamber: {geometry.discharges_into_prechamber}",
        f"Frozen engine injector face diameter: {engine_geometry.injector_face_diameter_m * 1000.0:.2f} mm",
        f"Equivalent injector area carried by the baseline geometry: {engine_geometry.injector_equivalent_area_m2 * 1.0e6:.3f} mm^2",
        f"Candidate count evaluated: {candidate_count}",
        "",
        "Requirement:",
        f"  source={requirement['source']}, total area={requirement['required_total_area_m2'] * 1.0e6:.3f} mm^2, effective CdA={requirement['required_effective_cda_m2'] * 1.0e6:.3f} mm^2",
        "",
        "Back-calculated reduced-order model:",
        f"  Cd={effective_model.estimated_cd:.4f}, area={effective_model.total_geometric_area_m2 * 1.0e6:.3f} mm^2, effective CdA={effective_model.effective_cda_m2 * 1.0e6:.3f} mm^2",
        "",
        "Warnings:",
        *(geometry.warnings or ["None"]),
        "",
        "Notes:",
        *(geometry.notes or ["None"]),
    ]


def write_injector_outputs(
    output_dir: str | Path,
    *,
    engine_geometry: GeometryDefinition,
    design_point: InjectorDesignPoint,
    requirement: dict[str, Any],
    injector_geometry: InjectorGeometryDefinition,
    effective_model: InjectorEffectiveModel,
    candidates: list[InjectorCandidateEvaluation],
) -> None:
    """Write JSON, CSV, text, and SVG outputs for a synthesized showerhead injector."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    candidate_rows = _candidate_rows(candidates)
    write_json(destination / "injector_geometry.json", injector_geometry.to_dict())
    write_rows_csv(destination / "injector_geometry.csv", _flatten_geometry_for_csv(injector_geometry))
    write_rows_csv(destination / "injector_rings.csv", _ring_rows(injector_geometry))
    write_rows_csv(destination / "injector_candidates.csv", candidate_rows)
    write_json(destination / "injector_design_point.json", design_point.to_dict())
    write_json(destination / "injector_requirement.json", requirement)
    write_json(destination / "injector_effective_model.json", effective_model.to_dict())
    write_mapping_csv(
        destination / "injector_summary.csv",
        {
            "injector_type": injector_geometry.injector_type,
            "design_condition_source": design_point.source,
            "hole_count": injector_geometry.hole_count,
            "hole_diameter_mm": injector_geometry.hole_diameter_m * 1000.0,
            "total_geometric_area_mm2": injector_geometry.total_geometric_area_m2 * 1.0e6,
            "estimated_effective_cda_mm2": injector_geometry.estimated_effective_cda_m2 * 1.0e6,
            "estimated_cd": injector_geometry.estimated_cd,
            "plate_thickness_mm": injector_geometry.plate_thickness_m * 1000.0,
            "hole_ld_ratio": injector_geometry.hole_ld_ratio,
            "ring_count": injector_geometry.ring_count,
            "minimum_ligament_mm": injector_geometry.min_ligament_m * 1000.0,
            "minimum_edge_margin_mm": injector_geometry.min_edge_margin_m * 1000.0,
            "plenum_depth_mm": injector_geometry.plenum_depth_m * 1000.0,
            "plenum_volume_cc": injector_geometry.plenum_volume_m3 * 1.0e6,
            "design_delta_p_bar": injector_geometry.design_injector_delta_p_pa / 1.0e5,
            "design_hole_velocity_m_s": injector_geometry.design_hole_velocity_m_s,
            "injector_geometry_valid": injector_geometry.injector_geometry_valid,
        },
    )
    (destination / "injector_summary.txt").write_text(
        "\n".join(
            _summary_lines(
                engine_geometry=engine_geometry,
                design_point=design_point,
                requirement=requirement,
                geometry=injector_geometry,
                effective_model=effective_model,
                candidate_count=len(candidates),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    _write_pattern_svg(destination / "injector_pattern.svg", injector_geometry)

    if candidate_rows:
        hole_counts = [row["hole_count"] for row in candidate_rows]
        write_line_plot(
            destination / "injector_candidate_cda_vs_hole_count.svg",
            [
                {
                    "label": "Estimated CdA [mm^2]",
                    "x": hole_counts,
                    "y": [row["estimated_effective_cda_mm2"] for row in candidate_rows],
                },
                {
                    "label": "Required CdA [mm^2]",
                    "x": hole_counts,
                    "y": [injector_geometry.required_effective_cda_m2 * 1.0e6 for _ in candidate_rows],
                },
            ],
            "Injector Candidates | Effective CdA vs Hole Count",
            "Hole Count [-]",
            "Effective CdA [mm^2]",
        )
        write_line_plot(
            destination / "injector_candidate_diameter_vs_hole_count.svg",
            [
                {
                    "label": "Hole diameter [mm]",
                    "x": hole_counts,
                    "y": [row["hole_diameter_mm"] for row in candidate_rows],
                },
            ],
            "Injector Candidates | Hole Diameter vs Hole Count",
            "Hole Count [-]",
            "Hole Diameter [mm]",
        )
