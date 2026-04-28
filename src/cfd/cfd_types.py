"""Typed models for CFD campaign planning, case export, and correction reuse."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class CfdTargetDefinition:
    """One recommended CFD target in the ordered campaign."""

    target_name: str
    target_category: str
    priority_rank: int
    objective_description: str
    why_reduced_order_is_insufficient: str
    required_geometry_scope: str
    required_operating_points: list[str]
    recommended_fidelity: str
    recommended_flow_type: str
    expected_outputs: list[str]
    downstream_models_affected: list[str]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CfdOperatingPoint:
    """One reduced-order operating point selected for a CFD target."""

    operating_point_name: str
    source_stage: str
    time_s: float | None
    chamber_pressure_pa: float | None
    injector_inlet_pressure_pa: float | None
    mass_flow_kg_s: float | None
    oxidizer_mass_flow_kg_s: float | None
    fuel_mass_flow_kg_s: float | None
    chamber_temp_k: float | None
    ambient_pressure_pa: float | None
    fluid_properties_reference: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CfdBoundaryConditionPackage:
    """Boundary-condition summary exported for external CFD setup."""

    case_name: str
    inlet_definitions: list[dict[str, Any]]
    outlet_definitions: list[dict[str, Any]]
    wall_assumptions: dict[str, Any]
    symmetry_assumptions: dict[str, Any]
    turbulence_placeholder_settings: dict[str, Any]
    thermal_bc_placeholders: dict[str, Any]
    species_definitions: list[dict[str, Any]]
    notes: list[str] = field(default_factory=list)
    validity_flags: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CfdGeometryPackage:
    """Geometry-scope metadata exported for a CFD case."""

    geometry_scope: str
    source_geometry_references: dict[str, str]
    exported_surfaces_or_regions: list[str]
    dimensional_metadata: dict[str, Any]
    simplification_notes: list[str] = field(default_factory=list)
    meshing_notes: list[str] = field(default_factory=list)
    validity_flags: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CfdCaseDefinition:
    """One concrete CFD case built from a target and operating point."""

    case_id: str
    target_definition: CfdTargetDefinition
    operating_point: CfdOperatingPoint
    geometry_package: CfdGeometryPackage
    boundary_conditions: CfdBoundaryConditionPackage
    recommended_solver_class: str
    priority_rank: int
    export_paths: dict[str, str]
    status: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CfdResultSummary:
    """Summarized external CFD result used for correction ingestion."""

    case_id: str
    solver_used: str | None
    completion_status: str
    result_source: str
    extracted_key_outputs: dict[str, Any] = field(default_factory=dict)
    comparison_to_reduced_order: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "CfdResultSummary":
        normalized = dict(payload)
        normalized["solver_used"] = None if normalized.get("solver_used") is None else str(normalized["solver_used"])
        normalized["completion_status"] = str(normalized.get("completion_status", "unknown"))
        normalized["result_source"] = str(normalized.get("result_source", "external_summary"))
        normalized["extracted_key_outputs"] = dict(normalized.get("extracted_key_outputs", {}))
        normalized["comparison_to_reduced_order"] = dict(normalized.get("comparison_to_reduced_order", {}))
        normalized["warnings"] = [str(item) for item in normalized.get("warnings", [])]
        normalized["notes"] = [str(item) for item in normalized.get("notes", [])]
        return cls(**normalized)


@dataclass(frozen=True)
class CfdCorrectionPackage:
    """Reusable reduced-order correction derived from one or more CFD cases."""

    correction_type: str
    source_case_id: str
    valid_operating_range: dict[str, Any]
    correction_data: dict[str, Any]
    downstream_target_module: str
    notes: list[str] = field(default_factory=list)
    confidence_level: str = "placeholder"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "CfdCorrectionPackage":
        normalized = dict(payload)
        normalized["valid_operating_range"] = dict(normalized.get("valid_operating_range", {}))
        normalized["correction_data"] = dict(normalized.get("correction_data", {}))
        normalized["notes"] = [str(item) for item in normalized.get("notes", [])]
        normalized["confidence_level"] = str(normalized.get("confidence_level", "placeholder"))
        return cls(**normalized)


@dataclass(frozen=True)
class CfdCampaignPlan:
    """Top-level ordered CFD campaign recommendation."""

    campaign_name: str
    case_source: str
    corrections_source: str
    targets: list[CfdTargetDefinition]
    stage_order: list[str]
    recommended_next_case_id: str | None
    recommended_next_target_name: str | None
    ingested_result_case_ids: list[str] = field(default_factory=list)
    validity_flags: dict[str, bool] = field(default_factory=dict)
    cfd_plan_valid: bool = True
    warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
