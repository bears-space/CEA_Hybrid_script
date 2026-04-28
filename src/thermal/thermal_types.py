"""Typed thermal-sizing models for first-pass engine thermal checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ThermalMaterialDefinition:
    """Thermal material properties used by the reduced-order thermal layer."""

    material_name: str
    density_kg_m3: float
    conductivity_w_mk: float
    heat_capacity_j_kgk: float
    diffusivity_m2_s: float | None = None
    emissivity: float | None = None
    max_service_temp_k: float | None = None
    melt_or_softening_temp_k: float | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ThermalDesignPolicy:
    """Configuration and assumptions for reduced-order engine thermal sizing."""

    gas_side_htc_model: str
    throat_htc_multiplier: float
    injector_face_htc_multiplier: float
    use_lumped_wall_model: bool
    wall_model_type: str
    inner_wall_node_count: int
    outer_convection_model: str
    outer_h_guess_w_m2k: float
    outer_ambient_temp_k: float
    radiation_enabled: bool
    surface_emissivity: float
    service_temp_margin_k: float
    sacrificial_liner_allowed: bool
    sacrificial_throat_insert_allowed: bool
    temperature_limit_basis: str
    thermal_roundup_increment_m: float
    minimum_protection_thickness_m: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ThermalLoadCase:
    """Transient thermal load case derived from solver histories."""

    case_name: str
    source_stage: str
    time_series_reference: str
    chamber_pressure_pa_time: list[float]
    mdot_total_kg_s_time: list[float]
    mdot_ox_kg_s_time: list[float]
    mdot_f_kg_s_time: list[float]
    of_time: list[float]
    cstar_time: list[float]
    cf_time: list[float]
    chamber_temp_k_time: list[float]
    gamma_time: list[float]
    throat_area_m2: float
    area_ratio: float
    burn_time_s: float
    ambient_pressure_pa: float
    time_s: list[float] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegionThermalResult:
    """Per-region thermal result and reduced-order transient histories."""

    region_name: str
    material_name: str
    selected_wall_thickness_m: float
    peak_heat_flux_w_m2: float
    peak_inner_wall_temp_k: float
    peak_outer_wall_temp_k: float | None
    max_allowable_temp_k: float
    thermal_margin_k: float
    governing_time_s: float
    wall_biot_number_peak: float
    valid: bool
    time_history_s: list[float] = field(default_factory=list)
    gas_side_htc_history_w_m2k: list[float] = field(default_factory=list)
    heat_flux_history_w_m2: list[float] = field(default_factory=list)
    inner_wall_temp_history_k: list[float] = field(default_factory=list)
    outer_wall_temp_history_k: list[float] = field(default_factory=list)
    model_assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChamberThermalResult:
    """Thermal result for a chamber-like cylindrical region."""

    region: RegionThermalResult
    inner_surface_area_m2: float
    gas_reference_temp_k: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NozzleThermalResult:
    """Thermal result for a nozzle region."""

    region: RegionThermalResult
    axial_length_m: float
    characteristic_diameter_m: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InjectorFaceThermalResult:
    """Thermal result for the injector hot face placeholder."""

    region: RegionThermalResult
    active_face_diameter_m: float
    open_area_ratio: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ThermalProtectionSizingResult:
    """Optional liner or throat-insert placeholder sizing result."""

    protection_name: str
    protected_region: str
    material_name: str
    required_thickness_m: float
    selected_thickness_m: float
    mass_estimate_kg: float
    reduced_peak_inner_wall_temp_k: float
    thermal_margin_k: float
    valid: bool
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ThermalSizingResult:
    """Top-level thermal sizing output for later workflow reuse."""

    governing_load_case: ThermalLoadCase
    chamber_region_result: ChamberThermalResult
    prechamber_result: ChamberThermalResult | None
    postchamber_result: ChamberThermalResult | None
    throat_result: NozzleThermalResult
    diverging_nozzle_result: NozzleThermalResult
    injector_face_result: InjectorFaceThermalResult | None
    optional_liner_result: ThermalProtectionSizingResult | None
    optional_throat_insert_result: ThermalProtectionSizingResult | None
    selected_materials: dict[str, str]
    design_policy: ThermalDesignPolicy
    case_summaries: list[dict[str, Any]]
    total_thermal_protection_mass_estimate_kg: float
    summary_margins: dict[str, float]
    validity_flags: dict[str, bool]
    thermal_valid: bool
    canonical_state: dict[str, Any] = field(default_factory=dict)
    canonical_region_reports: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
