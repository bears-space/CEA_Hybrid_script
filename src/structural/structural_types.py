"""Typed structural-sizing models for first-pass engine hardware checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class MaterialDefinition:
    """Material properties and derived allowable used by the structural layer."""

    material_name: str
    density_kg_m3: float
    yield_strength_pa: float
    ultimate_strength_pa: float
    allowable_stress_pa: float
    youngs_modulus_pa: float | None = None
    poisson_ratio: float | None = None
    max_service_temp_k: float | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StructuralDesignPolicy:
    """First-pass structural design factors and selection policy."""

    allowable_basis: str
    yield_safety_factor: float
    ultimate_safety_factor: float
    proof_factor: float
    burst_factor: float
    thin_wall_switch_ratio: float
    minimum_wall_thickness_m: float
    minimum_flange_thickness_m: float
    thickness_roundup_increment_m: float
    default_bolt_preload_fraction: float
    closure_model_type: str
    injector_plate_model_type: str
    nozzle_mount_model_type: str
    mass_roundup_factor: float
    corrosion_or_manufacturing_allowance_m: float
    closure_style: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StructuralLoadCase:
    """Explicit structural load case derived from the engine workflow outputs."""

    case_name: str
    source_stage: str
    chamber_pressure_pa: float
    injector_upstream_pressure_pa: float
    injector_delta_p_pa: float
    feed_delta_p_pa: float
    tank_pressure_pa: float | None
    ambient_pressure_pa: float
    axial_force_n: float
    nozzle_separating_force_n: float
    closure_separating_force_n: float
    time_s: float | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChamberSizingResult:
    """Pressure-vessel sizing output for the chamber shell."""

    material_name: str
    allowable_stress_pa: float
    chamber_pressure_pa: float
    chamber_radius_m: float
    required_thickness_m: float
    selected_thickness_m: float
    hoop_stress_pa: float
    axial_stress_pa: float
    governing_stress_pa: float
    margin_to_allowable: float
    thin_wall_ratio: float
    thin_wall_valid: bool
    method_used: str
    valid: bool
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClosureSizingResult:
    """First-pass circular-plate sizing result for a closure or flange-like plate."""

    closure_name: str
    material_name: str
    allowable_stress_pa: float
    chamber_pressure_pa: float
    loaded_diameter_m: float
    projected_area_m2: float
    separating_force_n: float
    required_thickness_m: float
    selected_thickness_m: float
    estimated_bending_stress_pa: float
    margin_to_allowable: float
    model_type: str
    valid: bool
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InjectorPlateSizingResult:
    """Conservative injector-plate structural placeholder check."""

    material_name: str
    allowable_stress_pa: float
    pressure_delta_pa: float
    unsupported_diameter_m: float
    hole_count: int | None
    hole_diameter_m: float | None
    open_area_ratio: float
    perforation_stress_multiplier: float
    required_thickness_m: float
    selected_thickness_m: float
    estimated_bending_stress_pa: float
    margin_to_allowable: float
    model_type: str
    valid: bool
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FastenerSizingResult:
    """High-level closure-retention check for bolted or tie-rod concepts."""

    retention_type: str
    material_name: str | None
    separating_force_n: float
    fastener_count: int
    nominal_diameter_m: float | None
    tensile_area_per_fastener_m2: float | None
    external_load_per_fastener_n: float | None
    preload_target_per_fastener_n: float | None
    required_fastener_count: int | None
    allowable_tensile_stress_pa: float | None
    estimated_tensile_stress_pa: float | None
    margin_to_allowable: float | None
    preload_margin: float | None
    valid: bool
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NozzleMountSizingResult:
    """First-pass aft interface and nozzle-retention placeholder sizing result."""

    material_name: str
    allowable_stress_pa: float
    chamber_pressure_pa: float
    loaded_diameter_m: float
    nozzle_separating_force_n: float
    required_thickness_m: float
    selected_thickness_m: float
    estimated_bending_stress_pa: float
    margin_to_allowable: float
    model_type: str
    valid: bool
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GrainSupportSizingResult:
    """Fuel-grain support and retention placeholder checks."""

    retention_concept: str
    initial_web_thickness_m: float
    final_web_thickness_m: float | None
    chamber_radial_clearance_m: float
    grain_length_m: float
    grain_outer_radius_m: float
    grain_slenderness_ratio: float
    web_slenderness_ratio: float
    valid: bool
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StructuralSizingResult:
    """Top-level structural sizing output for later reuse by other workflow layers."""

    selected_materials: dict[str, str]
    design_policy: StructuralDesignPolicy
    governing_load_case: StructuralLoadCase
    chamber_wall_result: ChamberSizingResult
    forward_closure_result: ClosureSizingResult
    aft_closure_result: ClosureSizingResult
    injector_plate_result: InjectorPlateSizingResult
    fastener_result: FastenerSizingResult
    nozzle_mount_result: NozzleMountSizingResult
    grain_support_result: GrainSupportSizingResult
    mass_breakdown_kg: dict[str, float]
    total_structural_mass_estimate_kg: float
    summary_margins: dict[str, float | None]
    validity_flags: dict[str, bool]
    structural_valid: bool
    canonical_state: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
