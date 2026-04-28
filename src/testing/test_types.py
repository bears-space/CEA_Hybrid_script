"""Typed models for test planning, ingestion, comparison, calibration, and readiness."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TestStageDefinition:
    """One ordered stage in the recommended development test campaign."""

    stage_name: str
    stage_order: int
    stage_category: str
    objective_description: str
    required_predecessors: list[str]
    key_questions_to_answer: list[str]
    success_metrics: list[str]
    required_measurements: list[str]
    recommended_article_types: list[str]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TestCampaignPlan:
    """Top-level ordered test campaign recommendation."""

    campaign_name: str
    campaign_source: str
    stages: list[TestStageDefinition]
    recommended_next_stage: str | None
    recommended_next_test: str | None
    uncertainty_focus: list[str]
    validity_flags: dict[str, bool]
    test_progression_valid: bool
    warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TestArticleDefinition:
    """Traceable definition for one test article or rig."""

    article_id: str
    article_scale: str
    article_type: str
    source_geometry_reference: str
    stage_name: str
    geometric_scaling_notes: list[str]
    injector_reference: str | None
    nozzle_reference: str | None
    material_stack_reference: str
    target_burn_time_s: float | None
    target_operating_point_source: str
    representative_for_baseline: bool
    intentional_differences: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InstrumentationChannel:
    """One recommended or required measurement channel."""

    channel_name: str
    sensor_type: str
    units: str
    sampling_rate_hz: float
    location_description: str
    required_flag: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InstrumentationPlan:
    """Instrumentation recommendation and expected data schema for an article."""

    article_id: str
    channels: list[InstrumentationChannel]
    required_core_channels: list[str]
    optional_channels: list[str]
    synchronization_notes: list[str]
    data_file_expectations: list[str]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TestMatrixPoint:
    """One planned test point in the campaign matrix."""

    point_id: str
    article_id: str
    intended_stage: str
    target_operating_condition: str
    expected_pressure_range: list[float]
    expected_burn_time_s: float | None
    target_thrust_range: list[float] | None
    objective: str
    repeat_group: str | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TestDataset:
    """Structured ingested test dataset for one run."""

    run_id: str
    article_id: str
    stage_name: str
    data_source: str
    file_references: list[str]
    time_series_channels: dict[str, list[float]]
    metadata: dict[str, Any]
    cleaned_time_series_channels: dict[str, list[float]] = field(default_factory=dict)
    cleaning_notes: list[str] = field(default_factory=list)
    validity_flags: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TestRunSummary:
    """Derived summary metrics from a cleaned test run."""

    run_id: str
    article_id: str
    stage_name: str
    start_time: str | None
    achieved_burn_time_s: float
    peak_chamber_pressure_pa: float | None
    average_chamber_pressure_pa: float | None
    peak_thrust_n: float | None
    average_thrust_n: float | None
    total_impulse_ns: float | None
    oxidizer_used_kg: float | None
    fuel_used_kg: float | None
    ignition_time_s: float | None
    stop_reason: str | None
    anomalies: list[str]
    derived_metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelVsTestComparison:
    """Comparison of solver predictions against one measured test run."""

    run_id: str
    article_id: str
    stage_name: str
    model_source: str
    comparison_metrics: dict[str, Any]
    pressure_trace_error: dict[str, Any]
    thrust_trace_error: dict[str, Any]
    burn_time_error: dict[str, Any]
    impulse_error: dict[str, Any]
    regression_fit_error: dict[str, Any] | None = None
    thermal_indicator_error: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)
    validity_flags: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HotfireCalibrationPackage:
    """Reusable hot-fire-derived reduced-order correction package."""

    package_name: str
    source_run_ids: list[str]
    source_scale: str
    transferability: str
    fitted_regression_parameters: dict[str, Any]
    fitted_cstar_efficiency: float | None
    fitted_cf_or_nozzle_loss_correction: float | None
    ignition_delay_correction: float | None
    thermal_multiplier_correction: float | None
    valid_operating_range: dict[str, Any]
    confidence_level: str
    downstream_overrides: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProgressionGateResult:
    """Pass/fail decision gate for advancing to a later stage."""

    stage_name: str
    gate_name: str
    pass_fail: bool
    criteria_results: dict[str, Any]
    blocking_issues: list[str]
    recommended_next_actions: list[str]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReadinessSummary:
    """Overall current readiness to progress to the next planned test."""

    current_stage: str | None
    completed_stages: list[str]
    outstanding_blockers: list[str]
    recommended_next_test: str | None
    calibrated_model_state_reference: str | None
    overall_readiness_flag: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
