"""Geometry-scope packaging for external CFD case setup."""

from __future__ import annotations

from typing import Any, Mapping

from src.cfd.cfd_types import CfdGeometryPackage, CfdTargetDefinition
from src.injector_design.injector_types import InjectorGeometryDefinition
from src.sizing.geometry_types import GeometryDefinition


def build_cfd_geometry_package(
    target: CfdTargetDefinition,
    *,
    geometry: GeometryDefinition,
    injector_geometry: InjectorGeometryDefinition | None,
    cfd_config: Mapping[str, Any],
) -> CfdGeometryPackage:
    """Build the structured geometry package for one CFD target."""

    scope = target.required_geometry_scope
    source_refs = {"frozen_geometry": "geometry_definition.json"}
    if injector_geometry is not None:
        source_refs["injector_geometry"] = "injector_geometry.json"

    simplification_settings = dict(cfd_config.get("geometry_simplifications", {}))
    simplification_notes = [
        note
        for enabled, note in (
            (
                bool(simplification_settings.get("suppress_small_fillet_details", True)),
                "Suppress small fillets and edge-break details unless they materially affect the target.",
            ),
            (
                bool(simplification_settings.get("collapse_small_hole_chamfers", True)),
                "Collapse minor hole-chamfer details for early injector CFD unless a discharge-edge study is the actual objective.",
            ),
            (
                bool(simplification_settings.get("allow_periodic_sector_model", False)),
                "Periodic or sector-model simplifications are allowed if the injector-hole pattern and objective justify symmetry.",
            ),
            (
                bool(simplification_settings.get("truncate_far_downstream_volume", True)),
                "Truncate far-downstream volume and retain only the region needed to answer the local CFD question.",
            ),
        )
        if enabled
    ]
    meshing_notes = [
        "Resolve injector-hole entrances, likely vena-contracta regions, and wall-adjacent gradients commensurate with the chosen solver class.",
        "Retain named surfaces for inlets, outlets, symmetry planes, walls, and any thermal-monitoring regions.",
    ]

    regions_by_scope = {
        "injector_plenum_plate_short_downstream": [
            "feed_or_manifold_inlet",
            "injector_plenum_volume",
            "injector_plate_upstream_face",
            "injector_hole_passages",
            "short_downstream_discharge_volume",
        ],
        "injector_face_prechamber_grain_entrance": [
            "injector_hole_exits",
            "injector_face_hot_side",
            "prechamber_volume",
            "grain_entrance_plane",
            "initial_port_segment",
        ],
        "converging_throat_diverging_region": [
            "nozzle_inlet_plane",
            "converging_wall",
            "throat_region",
            "diverging_wall",
            "nozzle_exit_plane",
        ],
        "prechamber_grain_port_nozzle_segment": [
            "injector_face_hot_side",
            "prechamber_volume",
            "grain_port_volume",
            "postchamber_volume",
            "converging_throat_diverging_region",
        ],
    }
    dimensional_metadata: dict[str, Any] = {
        "chamber_id_m": float(geometry.chamber_id_m),
        "injector_face_diameter_m": float(geometry.injector_face_diameter_m),
        "prechamber_length_m": float(geometry.prechamber_length_m),
        "grain_length_m": float(geometry.grain_length_m),
        "postchamber_length_m": float(geometry.postchamber_length_m),
        "throat_diameter_m": float(geometry.throat_diameter_m),
        "nozzle_exit_diameter_m": float(geometry.nozzle_exit_diameter_m),
        "nozzle_area_ratio": float(geometry.nozzle_area_ratio),
        "converging_section_length_m": float(geometry.converging_section_length_m or 0.0),
        "converging_section_arc_length_m": float(geometry.converging_section_arc_length_m or 0.0),
        "nozzle_length_m": float(geometry.nozzle_length_m or 0.0),
        "nozzle_arc_length_m": float(geometry.nozzle_arc_length_m or 0.0),
        "nozzle_contour_style": str(geometry.nozzle_contour_style or "unspecified"),
        "injector_plate_thickness_m": float(geometry.injector_plate_thickness_m),
    }
    if injector_geometry is not None:
        dimensional_metadata.update(
            {
                "injector_hole_count": int(injector_geometry.hole_count),
                "injector_hole_diameter_m": float(injector_geometry.hole_diameter_m),
                "injector_active_face_diameter_m": float(injector_geometry.active_face_diameter_m),
                "injector_plenum_depth_m": float(injector_geometry.plenum_depth_m),
            }
        )

    validity_flags = {
        "frozen_geometry_available": geometry is not None,
        "injector_geometry_available_if_needed": (
            True
            if target.target_category not in {"injector_plenum", "headend_prechamber"}
            else injector_geometry is not None
        ),
        "geometry_scope_defined": scope in regions_by_scope,
    }
    if target.target_category == "injector_plenum" and injector_geometry is None:
        simplification_notes.append(
            "Injector target fell back to frozen-face dimensions because a synthesized injector geometry was not available."
        )

    return CfdGeometryPackage(
        geometry_scope=scope,
        source_geometry_references=source_refs,
        exported_surfaces_or_regions=list(regions_by_scope.get(scope, [scope])),
        dimensional_metadata=dimensional_metadata,
        simplification_notes=simplification_notes,
        meshing_notes=meshing_notes,
        validity_flags=validity_flags,
    )
