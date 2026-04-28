"""Calibration-package persistence and runtime back-integration helpers."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from src.hydraulic_validation.coldflow_types import CalibrationPackage
from src.io_utils import load_json


def load_calibration_package(path: str | Path) -> CalibrationPackage:
    """Load a serialized hydraulic calibration package."""

    return CalibrationPackage.from_mapping(load_json(path))


def calibration_path_from_config(config: Mapping[str, Any]) -> Path | None:
    section = dict(config.get("hydraulic_validation", {}))
    raw_path = str(section.get("calibration_package_path", "")).strip()
    if not raw_path:
        return None
    return Path(raw_path)


def apply_calibration_package_to_runtime(runtime: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    """Apply a saved calibration package to a prepared runtime payload."""

    hydraulic_config = dict(config.get("hydraulic_validation", {}))
    hydraulic_source = str(hydraulic_config.get("hydraulic_source", "nominal_uncalibrated"))
    if hydraulic_source == "nominal_uncalibrated":
        return dict(runtime)

    calibration_path = calibration_path_from_config(config)
    if calibration_path is None:
        if bool(hydraulic_config.get("allow_missing_calibration_package", True)):
            return dict(runtime)
        raise FileNotFoundError(
            "hydraulic_validation.calibration_package_path is required when hydraulic_source is calibrated."
        )
    if not calibration_path.exists():
        if bool(hydraulic_config.get("allow_missing_calibration_package", True)):
            return dict(runtime)
        raise FileNotFoundError(f"Hydraulic calibration package not found: {calibration_path}")

    package = load_calibration_package(calibration_path)
    updates = dict(package.recommended_parameter_updates)
    updated_runtime = dict(runtime)
    updated_feed = runtime["feed"]
    updated_injector = runtime["injector"]

    if updates.get("feed_pressure_drop_multiplier_calibrated") is not None:
        updated_feed = replace(
            updated_feed,
            pressure_drop_multiplier=float(updates["feed_pressure_drop_multiplier_calibrated"]),
        )
    elif updates.get("feed_loss_multiplier") is not None:
        updated_feed = replace(
            updated_feed,
            pressure_drop_multiplier=float(updated_feed.pressure_drop_multiplier) * float(updates["feed_loss_multiplier"]),
        )

    if hydraulic_source == "geometry_plus_coldflow":
        injector_multiplier = updates.get(
            "geometry_backcalc_correction_factor",
            updates.get("injector_cda_multiplier"),
        )
    else:
        injector_multiplier = updates.get("injector_cda_multiplier")
    if injector_multiplier is not None:
        updated_injector = replace(
            updated_injector,
            cd=float(updated_injector.cd) * float(injector_multiplier),
        )
    elif updates.get("injector_cd_calibrated") is not None:
        updated_injector = replace(
            updated_injector,
            cd=float(updates["injector_cd_calibrated"]),
        )

    updated_runtime["feed"] = updated_feed
    updated_runtime["injector"] = updated_injector
    derived = dict(updated_runtime.get("derived", {}))
    derived.update(
        {
            "hydraulic_source": hydraulic_source,
            "hydraulic_calibration_package_path": str(calibration_path),
            "hydraulic_calibration_valid": bool(package.calibration_valid),
            "hydraulic_calibration_fluid": package.calibration_fluid,
            "hydraulic_recommended_model_source": package.recommended_model_source,
            "hydraulic_calibration_warning_count": len(package.warnings),
            "hydraulic_calibration_warnings": list(package.warnings),
            "feed_pressure_drop_multiplier": float(updated_feed.pressure_drop_multiplier),
            "injector_cd": float(updated_injector.cd),
        }
    )
    if float(updated_injector.total_area_m2) > 0.0:
        derived["injector_effective_cda_mm2"] = (
            float(updated_injector.cd) * float(updated_injector.total_area_m2) * 1.0e6
        )
    updated_runtime["derived"] = derived
    updated_runtime["hydraulic_calibration_package"] = package
    return updated_runtime
