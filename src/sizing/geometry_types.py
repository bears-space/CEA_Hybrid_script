"""Structured geometry objects for the baseline freeze layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class GeometryDefinition:
    """Frozen first-pass engine geometry passed to later workflow stages."""

    chamber_id_m: float
    injector_face_diameter_m: float
    prechamber_length_m: float
    grain_length_m: float
    port_radius_initial_m: float
    grain_outer_radius_m: float
    postchamber_length_m: float
    throat_diameter_m: float
    nozzle_exit_diameter_m: float
    nozzle_area_ratio: float
    injector_plate_thickness_m: float
    chamber_wall_thickness_guess_m: float
    total_chamber_length_m: float
    free_volume_initial_m3: float
    lstar_initial_m: float
    single_port_baseline: bool
    prechamber_enabled: bool
    postchamber_enabled: bool
    axial_showerhead_injector_baseline: bool
    injector_discharges_to_prechamber: bool
    port_count: int
    radial_web_initial_m: float
    chamber_cross_section_area_m2: float
    injector_face_area_m2: float
    throat_area_m2: float
    nozzle_exit_area_m2: float
    injector_equivalent_area_m2: float
    chamber_inner_diameter_including_liner_m: float | None = None
    chamber_outer_diameter_including_liner_m: float | None = None
    chamber_inner_diameter_excluding_liner_m: float | None = None
    chamber_outer_diameter_excluding_liner_m: float | None = None
    fuel_inner_diameter_m: float | None = None
    fuel_outer_diameter_m: float | None = None
    inner_liner_thickness_m: float | None = None
    injector_hole_count: int | None = None
    injector_total_hole_area_m2: float | None = None
    injector_hole_diameter_m: float | None = None
    converging_throat_half_angle_deg: float | None = None
    diverging_throat_half_angle_deg: float | None = None
    throat_blend_radius_m: float | None = None
    converging_section_length_m: float | None = None
    converging_section_arc_length_m: float | None = None
    converging_straight_length_m: float | None = None
    converging_blend_arc_length_m: float | None = None
    nozzle_length_m: float | None = None
    nozzle_arc_length_m: float | None = None
    nozzle_straight_length_m: float | None = None
    nozzle_blend_arc_length_m: float | None = None
    nozzle_contour_style: str | None = None
    nozzle_profile: dict[str, Any] = field(default_factory=dict)
    nominal_pc_bar: float | None = None
    nominal_thrust_avg_n: float | None = None
    nominal_isp_avg_s: float | None = None
    nominal_burn_time_s: float | None = None
    nominal_constraint_pass: bool | None = None
    corner_cases_all_pass: bool | None = None
    sensitivity_driver_metric: str | None = None
    sensitivity_top_parameter: str | None = None
    cea_reference: dict[str, Any] | None = None
    source_summary: dict[str, Any] = field(default_factory=dict)
    engine_state: dict[str, Any] = field(default_factory=dict)
    geometry_valid: bool = True
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    solver_report: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "GeometryDefinition":
        normalized = dict(payload)
        normalized["nozzle_profile"] = dict(normalized.get("nozzle_profile", {}))
        normalized["source_summary"] = dict(normalized.get("source_summary", {}))
        normalized["engine_state"] = dict(normalized.get("engine_state", {}))
        normalized["checks"] = dict(normalized.get("checks", {}))
        normalized["warnings"] = list(normalized.get("warnings", []))
        normalized["failure_reasons"] = list(normalized.get("failure_reasons", []))
        normalized["solver_report"] = dict(normalized.get("solver_report", {}))
        normalized["notes"] = list(normalized.get("notes", []))
        if normalized.get("cea_reference") is not None:
            normalized["cea_reference"] = dict(normalized["cea_reference"])
        return cls(**normalized)
