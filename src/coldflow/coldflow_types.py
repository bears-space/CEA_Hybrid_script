"""Typed data models for the Step 5 hydraulic and cold-flow workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ColdFlowRigDefinition:
    """Description of the bench or rig used to acquire cold-flow data."""

    test_mode: str
    pressure_tap_locations: dict[str, str] = field(default_factory=dict)
    line_geometry_known: bool = False
    valve_filter_notes: list[str] = field(default_factory=list)
    injector_geometry_reference: str | None = None
    calibration_assumptions: list[str] = field(default_factory=list)
    surrogate_fluid_used: bool = False
    intended_application: str | None = None
    notes: list[str] = field(default_factory=list)
    feed_model_override: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "ColdFlowRigDefinition":
        normalized = dict(payload)
        normalized["pressure_tap_locations"] = dict(normalized.get("pressure_tap_locations", {}))
        normalized["valve_filter_notes"] = list(normalized.get("valve_filter_notes", []))
        normalized["calibration_assumptions"] = list(normalized.get("calibration_assumptions", []))
        normalized["notes"] = list(normalized.get("notes", []))
        normalized["feed_model_override"] = dict(normalized.get("feed_model_override", {}))
        return cls(**normalized)


@dataclass(frozen=True)
class ColdFlowPoint:
    """One measured cold-flow operating point."""

    test_id: str
    point_index: int | None = None
    timestamp: str | None = None
    fluid_name: str | None = None
    fluid_temperature_k: float | None = None
    fluid_density_kg_m3: float | None = None
    upstream_pressure_pa: float | None = None
    injector_inlet_pressure_pa: float | None = None
    downstream_pressure_pa: float | None = None
    measured_delta_p_feed_pa: float | None = None
    measured_delta_p_injector_pa: float | None = None
    measured_mdot_kg_s: float | None = None
    measurement_uncertainty: dict[str, float] = field(default_factory=dict)
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ColdFlowDataset:
    """Validated cold-flow dataset and associated rig metadata."""

    dataset_name: str
    test_mode: str
    points: list[ColdFlowPoint]
    rig_definition: ColdFlowRigDefinition
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "test_mode": self.test_mode,
            "points": [point.to_dict() for point in self.points],
            "rig_definition": self.rig_definition.to_dict(),
            "metadata": dict(self.metadata),
            "warnings": list(self.warnings),
        }

    def to_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for point in self.points:
            row = point.to_dict()
            if row["measurement_uncertainty"]:
                row["measurement_uncertainty"] = str(row["measurement_uncertainty"])
            rows.append(row)
        return rows


@dataclass(frozen=True)
class HydraulicPrediction:
    """Predicted hydraulic state for one cold-flow data point."""

    test_id: str
    point_index: int | None
    model_source: str
    fluid_name: str
    fluid_density_kg_m3: float
    predicted_mdot_kg_s: float
    predicted_feed_delta_p_pa: float
    predicted_injector_delta_p_pa: float
    predicted_injector_inlet_pressure_pa: float
    predicted_effective_cda_m2: float
    predicted_injector_cd: float
    predicted_total_area_m2: float
    predicted_total_pressure_drop_pa: float
    predicted_per_hole_velocity_m_s: float
    pressure_solution_source: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HydraulicResidual:
    """Prediction-minus-measurement residuals for one cold-flow data point."""

    test_id: str
    point_index: int | None
    model_source: str
    measured_mdot_kg_s: float | None = None
    predicted_mdot_kg_s: float | None = None
    mdot_error_kg_s: float | None = None
    mdot_error_percent: float | None = None
    measured_feed_delta_p_pa: float | None = None
    predicted_feed_delta_p_pa: float | None = None
    feed_delta_p_error_pa: float | None = None
    feed_delta_p_error_percent: float | None = None
    measured_injector_delta_p_pa: float | None = None
    predicted_injector_delta_p_pa: float | None = None
    injector_delta_p_error_pa: float | None = None
    injector_delta_p_error_percent: float | None = None
    measured_injector_inlet_pressure_pa: float | None = None
    predicted_injector_inlet_pressure_pa: float | None = None
    injector_inlet_pressure_error_pa: float | None = None
    injector_inlet_pressure_error_percent: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InjectorCalibrationResult:
    """Scalar injector calibration against cold-flow data."""

    calibration_mode: str
    base_model_source: str
    calibration_fluid: str
    data_points_used: int
    injector_cd_calibrated: float
    injector_effective_cda_calibrated_m2: float
    injector_cda_multiplier: float
    geometry_backcalc_correction_factor: float | None = None
    residual_statistics: dict[str, Any] = field(default_factory=dict)
    validation_flags: dict[str, bool] = field(default_factory=dict)
    calibration_valid: bool = True
    warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FeedCalibrationResult:
    """Scalar feed-system calibration against cold-flow data."""

    calibration_mode: str
    calibration_fluid: str
    data_points_used: int
    feed_loss_multiplier: float
    feed_pressure_drop_multiplier_calibrated: float
    equivalent_total_loss_factor_calibrated: float
    residual_statistics: dict[str, Any] = field(default_factory=dict)
    validation_flags: dict[str, bool] = field(default_factory=dict)
    calibration_valid: bool = True
    warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class JointCalibrationResult:
    """Combined feed and injector calibration with identifiability tracking."""

    calibration_mode: str
    base_model_source: str
    calibration_fluid: str
    data_points_used: int
    feed_loss_multiplier: float
    feed_pressure_drop_multiplier_calibrated: float
    equivalent_total_loss_factor_calibrated: float
    injector_cd_calibrated: float
    injector_effective_cda_calibrated_m2: float
    injector_cda_multiplier: float
    geometry_backcalc_correction_factor: float | None = None
    residual_statistics: dict[str, Any] = field(default_factory=dict)
    validation_flags: dict[str, bool] = field(default_factory=dict)
    calibration_valid: bool = True
    warnings: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    feed_result: FeedCalibrationResult | None = None
    injector_result: InjectorCalibrationResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalibrationPackage:
    """Reusable calibration package for solver back-integration."""

    calibration_mode: str
    hydraulic_source: str
    recommended_model_source: str
    calibration_fluid: str
    surrogate_fluid_used: bool
    intended_application: str
    fitted_parameters: dict[str, Any]
    residual_statistics: dict[str, Any]
    validity_flags: dict[str, bool]
    calibration_valid: bool
    warnings: list[str]
    failure_reason: str | None
    reference_dataset_metadata: dict[str, Any]
    recommended_parameter_updates: dict[str, Any]
    feed_result: FeedCalibrationResult | None = None
    injector_result: InjectorCalibrationResult | None = None
    joint_result: JointCalibrationResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "CalibrationPackage":
        normalized = dict(payload)
        if normalized.get("feed_result") is not None:
            normalized["feed_result"] = FeedCalibrationResult(**dict(normalized["feed_result"]))
        if normalized.get("injector_result") is not None:
            normalized["injector_result"] = InjectorCalibrationResult(**dict(normalized["injector_result"]))
        if normalized.get("joint_result") is not None:
            joint = dict(normalized["joint_result"])
            if joint.get("feed_result") is not None:
                joint["feed_result"] = FeedCalibrationResult(**dict(joint["feed_result"]))
            if joint.get("injector_result") is not None:
                joint["injector_result"] = InjectorCalibrationResult(**dict(joint["injector_result"]))
            normalized["joint_result"] = JointCalibrationResult(**joint)
        normalized["warnings"] = list(normalized.get("warnings", []))
        normalized["fitted_parameters"] = dict(normalized.get("fitted_parameters", {}))
        normalized["residual_statistics"] = dict(normalized.get("residual_statistics", {}))
        normalized["validity_flags"] = dict(normalized.get("validity_flags", {}))
        normalized["reference_dataset_metadata"] = dict(normalized.get("reference_dataset_metadata", {}))
        normalized["recommended_parameter_updates"] = dict(normalized.get("recommended_parameter_updates", {}))
        return cls(**normalized)
