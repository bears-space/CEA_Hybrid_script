"""Typed models for nozzle off-design and environment assessment."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class AmbientEnvironmentCase:
    """One ambient environment case used for nozzle off-design evaluation."""

    case_name: str
    ambient_pressure_pa: float
    ambient_temperature_k: float | None = None
    altitude_m: float | None = None
    environment_type: str = "user_override"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NozzleOperatingPoint:
    """A single evaluated nozzle operating point at a given ambient condition."""

    operating_point_label: str
    time_s: float | None
    chamber_pressure_pa: float
    chamber_temp_k: float | None
    gamma: float | None
    molecular_weight: float | None
    total_mass_flow_kg_s: float
    throat_area_m2: float
    exit_area_m2: float
    area_ratio: float
    ambient_pressure_pa: float
    exit_pressure_pa: float
    exit_mach: float | None
    cf_actual: float
    thrust_n: float
    isp_s: float
    expansion_state: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NozzleOffDesignCase:
    """A pairing of an engine-state source with an ambient environment case."""

    case_name: str
    source_stage: str
    engine_result_reference: str
    ambient_case_reference: str
    use_transient_time_history: bool
    selected_time_indices: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SeparationRiskResult:
    """Reduced-order separation-risk and side-load placeholder assessment."""

    risk_level: str
    margin_metric: float
    likely_overexpanded: bool
    likely_underexpanded: bool
    startup_risk_flag: bool
    shutdown_risk_flag: bool
    separation_warning: str | None
    model_assumptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NozzleEnvironmentSummary:
    """Summary of nozzle behavior for one ambient environment case."""

    case_name: str
    environment_type: str
    ambient_pressure_pa: float
    ambient_temperature_k: float | None
    altitude_m: float | None
    average_thrust_n: float
    peak_thrust_n: float
    average_cf_actual: float
    average_isp_s: float
    min_exit_to_ambient_ratio: float | None
    max_exit_to_ambient_ratio: float | None
    dominant_expansion_state: str
    separation_risk_level: str
    ground_test_relevant: bool
    flight_relevant: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AmbientCaseEvaluationResult:
    """Detailed evaluated results for one ambient environment case."""

    ambient_case: AmbientEnvironmentCase
    offdesign_case: NozzleOffDesignCase
    operating_points: list[NozzleOperatingPoint]
    summary: NozzleEnvironmentSummary
    separation_result: SeparationRiskResult

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NozzleOffDesignResult:
    """Top-level nozzle off-design and environment assessment output."""

    governing_case: NozzleOffDesignCase
    ambient_case_results: list[AmbientCaseEvaluationResult]
    transient_results: dict[str, list[dict[str, Any]]]
    sea_level_summary: NozzleEnvironmentSummary | None
    vacuum_summary: NozzleEnvironmentSummary | None
    matched_altitude_summary: NozzleEnvironmentSummary | None
    separation_result: SeparationRiskResult
    recommendations: dict[str, Any]
    validity_flags: dict[str, bool]
    nozzle_offdesign_valid: bool
    warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
