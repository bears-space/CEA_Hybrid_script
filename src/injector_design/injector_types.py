"""Explicit data models for injector geometry synthesis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class InjectorDesignPoint:
    """Resolved injector sizing point used for showerhead synthesis."""

    source: str
    mdot_ox_kg_s: float
    injector_inlet_pressure_pa: float
    chamber_pressure_pa: float
    injector_delta_p_pa: float
    liquid_density_kg_m3: float
    tank_pressure_pa: float | None = None
    time_s: float | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InjectorRequirement:
    """Equivalent injector requirement extracted from the current reduced-order model."""

    source: str
    required_total_area_m2: float
    required_effective_cda_m2: float
    assumed_cd: float
    design_mdot_ox_kg_s: float
    design_delta_p_pa: float
    liquid_density_kg_m3: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InjectorRingDefinition:
    """One concentric ring in an axial showerhead injector pattern."""

    ring_index: int
    ring_radius_m: float
    holes_in_ring: int
    angular_offset_deg: float
    circumferential_spacing_m: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InjectorEffectiveModel:
    """Reduced-order injector model estimated back from a real geometry."""

    discharge_model: str
    estimated_cd: float
    total_geometric_area_m2: float
    effective_area_m2: float
    effective_cda_m2: float
    design_mdot_ox_kg_s: float
    design_delta_p_pa: float
    design_injector_inlet_pressure_pa: float
    design_chamber_pressure_pa: float
    design_hole_velocity_m_s: float
    area_ratio_to_requirement: float
    cda_ratio_to_requirement: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InjectorCandidateEvaluation:
    """Candidate summary used to compare showerhead layout options."""

    hole_count: int
    hole_diameter_m: float
    ring_count: int
    center_hole_enabled: bool
    total_geometric_area_m2: float
    estimated_effective_cda_m2: float
    actual_to_required_area_ratio: float
    actual_to_required_cda_ratio: float
    hole_ld_ratio: float
    min_ligament_m: float
    min_edge_margin_m: float
    open_area_ratio: float
    design_hole_velocity_m_s: float
    score: float
    valid: bool
    failure_reason: str | None = None

    def to_row(self) -> dict[str, Any]:
        return {
            "hole_count": self.hole_count,
            "hole_diameter_mm": self.hole_diameter_m * 1000.0,
            "ring_count": self.ring_count,
            "center_hole_enabled": self.center_hole_enabled,
            "total_geometric_area_mm2": self.total_geometric_area_m2 * 1.0e6,
            "estimated_effective_cda_mm2": self.estimated_effective_cda_m2 * 1.0e6,
            "actual_to_required_area_ratio": self.actual_to_required_area_ratio,
            "actual_to_required_cda_ratio": self.actual_to_required_cda_ratio,
            "hole_ld_ratio": self.hole_ld_ratio,
            "min_ligament_mm": self.min_ligament_m * 1000.0,
            "min_edge_margin_mm": self.min_edge_margin_m * 1000.0,
            "open_area_ratio": self.open_area_ratio,
            "design_hole_velocity_m_s": self.design_hole_velocity_m_s,
            "score": self.score,
            "valid": self.valid,
            "failure_reason": self.failure_reason,
        }


@dataclass(frozen=True)
class InjectorGeometryDefinition:
    """Selected manufacturable showerhead geometry and its reduced-order back-calculation."""

    injector_type: str
    design_condition_source: str
    requirement_source: str
    plate_outer_diameter_m: float
    active_face_diameter_m: float
    plate_thickness_m: float
    hole_count: int
    hole_diameter_m: float
    area_per_hole_m2: float
    total_geometric_area_m2: float
    estimated_cd: float
    estimated_effective_area_m2: float
    estimated_effective_cda_m2: float
    required_total_area_m2: float
    required_effective_cda_m2: float
    actual_to_required_area_ratio: float
    actual_to_required_cda_ratio: float
    hole_ld_ratio: float
    ring_count: int
    ring_definitions: list[InjectorRingDefinition]
    center_hole_enabled: bool
    min_ligament_m: float
    min_edge_margin_m: float
    plate_to_active_face_margin_m: float
    plenum_depth_m: float
    plenum_diameter_m: float
    plenum_volume_m3: float
    face_to_grain_distance_m: float
    discharges_into_prechamber: bool
    design_mdot_ox_kg_s: float
    design_liquid_density_kg_m3: float
    design_injector_delta_p_pa: float
    design_injector_inlet_pressure_pa: float
    design_chamber_pressure_pa: float
    design_hole_velocity_m_s: float
    geometric_open_area_ratio: float
    discharge_edge_model: str
    backcalculation_mode: str
    injector_geometry_valid: bool = True
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "InjectorGeometryDefinition":
        normalized = dict(payload)
        normalized["ring_definitions"] = [
            InjectorRingDefinition(**dict(item)) for item in normalized.get("ring_definitions", [])
        ]
        normalized["checks"] = dict(normalized.get("checks", {}))
        normalized["warnings"] = list(normalized.get("warnings", []))
        normalized["notes"] = list(normalized.get("notes", []))
        return cls(**normalized)
