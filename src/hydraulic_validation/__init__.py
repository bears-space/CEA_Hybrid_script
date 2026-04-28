"""Hydraulic validation and calibration utilities."""

from src.hydraulic_validation.calibration_store import apply_calibration_package_to_runtime, load_calibration_package
from src.hydraulic_validation.coldflow_types import (
    CalibrationPackage,
    ColdFlowDataset,
    ColdFlowPoint,
    ColdFlowRigDefinition,
    FeedCalibrationResult,
    HydraulicPrediction,
    HydraulicResidual,
    InjectorCalibrationResult,
    JointCalibrationResult,
)
from src.hydraulic_validation.data_ingest import load_coldflow_dataset
from src.hydraulic_validation.feed_calibration import calibrate_feed_model
from src.hydraulic_validation.hydraulic_predictor import (
    HydraulicModelContext,
    apply_parameter_updates_to_context,
    build_prediction_context,
    predict_dataset,
    predict_point,
)
from src.hydraulic_validation.injector_calibration import calibrate_injector_model
from src.hydraulic_validation.joint_calibration import calibrate_joint_model
from src.hydraulic_validation.workflow import (
    build_calibration_package,
    merge_hydraulic_validation_config,
    merge_coldflow_config,
    run_hydraulic_calibration_workflow,
    run_hydraulic_compare_workflow,
    run_hydraulic_prediction_workflow,
    run_coldflow_calibration_workflow,
    run_coldflow_compare_workflow,
    run_coldflow_prediction_workflow,
)

__all__ = [
    "CalibrationPackage",
    "ColdFlowDataset",
    "ColdFlowPoint",
    "ColdFlowRigDefinition",
    "FeedCalibrationResult",
    "HydraulicModelContext",
    "HydraulicPrediction",
    "HydraulicResidual",
    "InjectorCalibrationResult",
    "JointCalibrationResult",
    "apply_calibration_package_to_runtime",
    "apply_parameter_updates_to_context",
    "build_calibration_package",
    "build_prediction_context",
    "calibrate_feed_model",
    "calibrate_injector_model",
    "calibrate_joint_model",
    "load_calibration_package",
    "load_coldflow_dataset",
    "merge_hydraulic_validation_config",
    "merge_coldflow_config",
    "predict_dataset",
    "predict_point",
    "run_hydraulic_calibration_workflow",
    "run_hydraulic_compare_workflow",
    "run_hydraulic_prediction_workflow",
    "run_coldflow_calibration_workflow",
    "run_coldflow_compare_workflow",
    "run_coldflow_prediction_workflow",
]
