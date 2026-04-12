"""Cold-flow output export, reports, and lightweight plots."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from src.coldflow.coldflow_types import CalibrationPackage, ColdFlowDataset, FeedCalibrationResult, InjectorCalibrationResult, JointCalibrationResult
from src.io_utils import write_json
from src.post.csv_export import write_rows_csv
from src.post.plotting import write_line_plot, write_scatter_plot


def _summary_lines(
    *,
    dataset: ColdFlowDataset,
    calibration_mode: str,
    coldflow_config: Mapping[str, Any],
    baseline_stats: Mapping[str, Any],
    calibrated_stats: Mapping[str, Any] | None,
    calibration_package: CalibrationPackage | None,
) -> list[str]:
    fluid_section = dict(coldflow_config.get("fluid", {}))
    warnings = [*dataset.warnings]
    if calibration_package is not None:
        warnings.extend(calibration_package.warnings)
    lines = [
        "Cold-Flow Summary",
        f"Dataset: {dataset.dataset_name}",
        f"Test mode: {dataset.test_mode}",
        f"Fluid: {fluid_section.get('name', 'unspecified')}",
        f"Surrogate fluid: {bool(fluid_section.get('is_surrogate', False) or dataset.rig_definition.surrogate_fluid_used)}",
        f"Point count: {len(dataset.points)}",
        f"Calibration mode: {calibration_mode}",
        "",
        "Baseline residual metrics:",
        f"  mdot RMSE [%]: {baseline_stats.get('mdot_error_percent', {}).get('rmse')}",
        f"  feed dP RMSE [Pa]: {baseline_stats.get('feed_delta_p_error_pa', {}).get('rmse')}",
        f"  injector dP RMSE [Pa]: {baseline_stats.get('injector_delta_p_error_pa', {}).get('rmse')}",
    ]
    if calibrated_stats is not None:
        lines.extend(
            [
                "",
                "Calibrated residual metrics:",
                f"  mdot RMSE [%]: {calibrated_stats.get('mdot_error_percent', {}).get('rmse')}",
                f"  feed dP RMSE [Pa]: {calibrated_stats.get('feed_delta_p_error_pa', {}).get('rmse')}",
                f"  injector dP RMSE [Pa]: {calibrated_stats.get('injector_delta_p_error_pa', {}).get('rmse')}",
            ]
        )
    if calibration_package is not None:
        lines.extend(
            [
                "",
                "Recommended parameter updates:",
                *[
                    f"  {key}: {value}"
                    for key, value in calibration_package.recommended_parameter_updates.items()
                ],
                f"Recommended model source: {calibration_package.recommended_model_source}",
                f"Calibration valid: {calibration_package.calibration_valid}",
            ]
        )
    lines.extend(["", "Warnings:", *(warnings or ["None"])])
    return lines


def _parity_series(
    rows: Sequence[Mapping[str, Any]],
    *,
    measured_key: str,
    predicted_key: str,
    label: str,
) -> list[dict[str, Any]]:
    measured = [float(row[measured_key]) for row in rows if row.get(measured_key) is not None and row.get(predicted_key) is not None]
    predicted = [float(row[predicted_key]) for row in rows if row.get(measured_key) is not None and row.get(predicted_key) is not None]
    return [{"label": label, "x": measured, "y": predicted}]


def _residual_series(
    rows: Sequence[Mapping[str, Any]],
    *,
    x_key: str,
    y_key: str,
    label: str,
) -> list[dict[str, Any]]:
    x_values = [float(row[x_key]) for row in rows if row.get(x_key) is not None and row.get(y_key) is not None]
    y_values = [float(row[y_key]) for row in rows if row.get(x_key) is not None and row.get(y_key) is not None]
    return [{"label": label, "x": x_values, "y": y_values}]


def _before_after_error_series(
    before_rows: Sequence[Mapping[str, Any]],
    after_rows: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    before_y = [abs(float(row["mdot_error_percent"])) for row in before_rows if row.get("mdot_error_percent") is not None]
    series = [{"label": "Before", "x": list(range(len(before_y))), "y": before_y}]
    if after_rows is not None:
        after_y = [abs(float(row["mdot_error_percent"])) for row in after_rows if row.get("mdot_error_percent") is not None]
        series.append({"label": "After", "x": list(range(len(after_y))), "y": after_y})
    return series


def write_coldflow_outputs(
    output_dir: str | Path,
    *,
    dataset: ColdFlowDataset,
    coldflow_config: Mapping[str, Any],
    baseline_predictions: list[Mapping[str, Any]],
    baseline_residuals: list[Mapping[str, Any]],
    baseline_stats: Mapping[str, Any],
    calibrated_predictions: list[Mapping[str, Any]] | None = None,
    calibrated_residuals: list[Mapping[str, Any]] | None = None,
    calibrated_stats: Mapping[str, Any] | None = None,
    injector_result: InjectorCalibrationResult | None = None,
    feed_result: FeedCalibrationResult | None = None,
    joint_result: JointCalibrationResult | None = None,
    calibration_package: CalibrationPackage | None = None,
) -> Path:
    """Write the standard Step 5 cold-flow output bundle."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    write_rows_csv(destination / "dataset_cleaned.csv", dataset.to_rows())
    combined_predictions = [*baseline_predictions, *(calibrated_predictions or [])]
    combined_residuals = [*baseline_residuals, *(calibrated_residuals or [])]
    write_rows_csv(destination / "coldflow_predictions.csv", combined_predictions)
    write_rows_csv(destination / "coldflow_residuals.csv", combined_residuals)
    write_json(destination / "coldflow_dataset.json", dataset.to_dict())
    write_json(destination / "coldflow_baseline_stats.json", dict(baseline_stats))
    if calibrated_stats is not None:
        write_json(destination / "coldflow_calibrated_stats.json", dict(calibrated_stats))
    if injector_result is not None:
        write_json(destination / "injector_calibration.json", injector_result.to_dict())
    if feed_result is not None:
        write_json(destination / "feed_calibration.json", feed_result.to_dict())
    if joint_result is not None:
        write_json(destination / "joint_calibration.json", joint_result.to_dict())
    if calibration_package is not None:
        write_json(destination / "calibration_package.json", calibration_package.to_dict())
        write_json(destination / "calibrated_hydraulic_parameters.json", calibration_package.recommended_parameter_updates)
        override_payload = {
            "coldflow": {
                "hydraulic_source": calibration_package.recommended_model_source,
                "calibration_package_path": str(destination / "calibration_package.json"),
            }
        }
        if calibration_package.recommended_model_source == "geometry_plus_coldflow":
            override_payload["injector_geometry"] = {"solver_injector_source": "geometry_backcalculated"}
        write_json(destination / "updated_model_overrides.json", override_payload)

    active_residuals = calibrated_residuals or baseline_residuals
    write_scatter_plot(
        destination / "mdot_parity.svg",
        _parity_series(
            active_residuals,
            measured_key="measured_mdot_kg_s",
            predicted_key="predicted_mdot_kg_s",
            label="Predicted vs measured mdot",
        ),
        "Cold-Flow Mass-Flow Parity",
        "Measured mdot [kg/s]",
        "Predicted mdot [kg/s]",
        reference_line=True,
    )
    injector_parity_series = _parity_series(
        active_residuals,
        measured_key="measured_injector_delta_p_pa",
        predicted_key="predicted_injector_delta_p_pa",
        label="Predicted vs measured injector dP",
    )
    if injector_parity_series[0]["x"]:
        write_scatter_plot(
            destination / "injector_delta_p_parity.svg",
            injector_parity_series,
            "Cold-Flow Injector dP Parity",
            "Measured injector dP [Pa]",
            "Predicted injector dP [Pa]",
            reference_line=True,
        )
    feed_parity_series = _parity_series(
        active_residuals,
        measured_key="measured_feed_delta_p_pa",
        predicted_key="predicted_feed_delta_p_pa",
        label="Predicted vs measured feed dP",
    )
    if feed_parity_series[0]["x"]:
        write_scatter_plot(
            destination / "feed_delta_p_parity.svg",
            feed_parity_series,
            "Cold-Flow Feed dP Parity",
            "Measured feed dP [Pa]",
            "Predicted feed dP [Pa]",
            reference_line=True,
        )

    residual_flow_series = _residual_series(
        active_residuals,
        x_key="measured_mdot_kg_s",
        y_key="mdot_error_percent",
        label="Mass-flow residual",
    )
    if residual_flow_series[0]["x"]:
        write_scatter_plot(
            destination / "residual_vs_flow.svg",
            residual_flow_series,
            "Cold-Flow Residual vs Flow",
            "Measured mdot [kg/s]",
            "Mass-flow residual [%]",
            reference_line=False,
        )
    residual_pressure_series = _residual_series(
        active_residuals,
        x_key="measured_injector_delta_p_pa",
        y_key="mdot_error_percent",
        label="Mass-flow residual",
    )
    if residual_pressure_series[0]["x"]:
        write_scatter_plot(
            destination / "residual_vs_pressure.svg",
            residual_pressure_series,
            "Cold-Flow Residual vs Injector dP",
            "Measured injector dP [Pa]",
            "Mass-flow residual [%]",
            reference_line=False,
        )

    write_line_plot(
        destination / "calibration_before_vs_after.svg",
        _before_after_error_series(baseline_residuals, calibrated_residuals),
        "Cold-Flow | Absolute Mass-Flow Error Before vs After",
        "Point index [-]",
        "|Mass-flow error| [%]",
    )

    (destination / "coldflow_summary.txt").write_text(
        "\n".join(
            _summary_lines(
                dataset=dataset,
                calibration_mode=str(coldflow_config.get("calibration_mode", "predict_only")),
                coldflow_config=coldflow_config,
                baseline_stats=baseline_stats,
                calibrated_stats=calibrated_stats,
                calibration_package=calibration_package,
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return destination
