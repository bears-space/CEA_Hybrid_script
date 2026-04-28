"""High-level test-progression workflow orchestration."""

from __future__ import annotations

from typing import Any, Mapping

from src.hydraulic_validation.calibration_store import calibration_path_from_config
from src.io_utils import deep_merge
from src.testing.data_cleaning import clean_test_dataset
from src.testing.data_ingest import load_test_datasets
from src.testing.feature_extraction import summarize_test_dataset
from src.testing.hotfire_calibration import build_hotfire_calibration_packages
from src.testing.instrumentation_plan import build_instrumentation_plans
from src.testing.model_vs_test import compare_model_to_test, select_model_history
from src.testing.progression_gates import build_progression_gates
from src.testing.readiness import build_readiness_summary, determine_completed_stages
from src.testing.test_articles import build_test_articles
from src.testing.test_campaign import build_test_campaign_plan, build_test_stages
from src.testing.test_checks import build_testing_validity_flags, collect_testing_warnings
from src.testing.test_export import write_testing_outputs
from src.testing.test_matrix import build_test_matrix


def merge_testing_config(
    study_config: Mapping[str, Any],
    override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the testing config section after applying optional overrides."""

    override_section = dict(override or {})
    if "testing" in override_section and isinstance(override_section["testing"], Mapping):
        override_section = dict(override_section["testing"])
    return deep_merge(dict(study_config.get("testing", {})), override_section)


def _hydraulic_calibration_ready(study_config: Mapping[str, Any]) -> bool:
    hydraulic_config = dict(study_config.get("hydraulic_validation", {}))
    if str(hydraulic_config.get("hydraulic_source", "nominal_uncalibrated")) != "nominal_uncalibrated":
        return True
    path = calibration_path_from_config(study_config)
    return path is not None and path.exists()


def _build_trace_plot_payloads(
    cleaned_datasets,
    model_source: str,
    model_history: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not cleaned_datasets or not model_history:
        return []
    dataset = cleaned_datasets[0]
    channels = dataset.cleaned_time_series_channels or dataset.time_series_channels
    time_s = channels.get("time_s", [])
    model_time = list(model_history.get("integration_time_s", []))
    traces: list[dict[str, Any]] = []
    if "chamber_pressure_pa" in channels and model_history.get("pc_pa") is not None:
        traces.append(
            {
                "filename": "pressure_trace_model_vs_test",
                "title": f"Pressure Trace Model vs Test ({dataset.run_id}, {model_source})",
                "x_label": "Time [s]",
                "y_label": "Chamber Pressure [Pa]",
                "series": [
                    {"label": "Test", "x": time_s, "y": channels["chamber_pressure_pa"]},
                    {"label": "Model", "x": model_time, "y": list(model_history.get("pc_pa", []))},
                ],
            }
        )
    if "thrust_n" in channels and (model_history.get("thrust_n") is not None or model_history.get("thrust_transient_actual_n") is not None):
        traces.append(
            {
                "filename": "thrust_trace_model_vs_test",
                "title": f"Thrust Trace Model vs Test ({dataset.run_id}, {model_source})",
                "x_label": "Time [s]",
                "y_label": "Thrust [N]",
                "series": [
                    {"label": "Test", "x": time_s, "y": channels["thrust_n"]},
                    {"label": "Model", "x": model_time, "y": list(model_history.get("thrust_n", model_history.get("thrust_transient_actual_n", [])))},
                ],
            }
        )
    return traces


def run_testing_workflow(
    study_config: dict[str, Any],
    testing_config: Mapping[str, Any],
    output_dir: str,
    *,
    geometry: Any,
    nominal_payload: Mapping[str, Any],
    injector_geometry: Any | None = None,
    structural_result: Any | None = None,
    thermal_result: Any | None = None,
    nozzle_result: Any | None = None,
    cfd_payload: Mapping[str, Any] | None = None,
    ballistics_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the structured test-planning and model-feedback workflow."""

    stages = build_test_stages(testing_config)
    articles = build_test_articles(
        testing_config,
        stages=stages,
        geometry=geometry,
        injector_geometry=injector_geometry,
        nozzle_result=nozzle_result,
    )
    instrumentation_plans = build_instrumentation_plans(testing_config, articles)
    test_matrix = build_test_matrix(testing_config, articles=articles, nominal_payload=nominal_payload)
    datasets, ingest_warnings = load_test_datasets(testing_config, instrumentation_plans)
    cleaned_datasets = [clean_test_dataset(dataset, testing_config) for dataset in datasets]
    run_summaries = [summarize_test_dataset(dataset) for dataset in cleaned_datasets]

    model_source, model_history, model_metrics = select_model_history(
        testing_config,
        nominal_payload=nominal_payload,
        ballistics_payload=ballistics_payload,
    )
    comparisons = [
        compare_model_to_test(
            dataset,
            summary,
            model_source=model_source,
            model_history=model_history,
            model_metrics=model_metrics,
            thermal_result=thermal_result,
        )
        for dataset, summary in zip(cleaned_datasets, run_summaries)
    ]
    calibration_packages, selected_package, updated_config, calibration_warnings = build_hotfire_calibration_packages(
        testing_config,
        study_config=study_config,
        run_summaries=run_summaries,
        comparisons=comparisons,
    )
    hydraulic_ready = _hydraulic_calibration_ready(study_config)
    completed_stages = determine_completed_stages(run_summaries, hydraulic_calibration_ready=hydraulic_ready)
    gate_results = build_progression_gates(
        testing_config,
        stages=stages,
        run_summaries=run_summaries,
        comparisons=comparisons,
        structural_result=structural_result,
        thermal_result=thermal_result,
        nozzle_result=nozzle_result,
        hydraulic_calibration_ready=hydraulic_ready,
        cfd_context_available=cfd_payload is not None,
        selected_calibration_package=selected_package,
    )
    validity_flags = build_testing_validity_flags(
        testing_config,
        stages=stages,
        articles=articles,
        instrumentation_plans=instrumentation_plans,
        datasets=cleaned_datasets,
        comparisons=comparisons,
        gate_results=gate_results,
    )
    warnings = collect_testing_warnings(datasets=cleaned_datasets, calibration_warnings=[*ingest_warnings, *calibration_warnings])
    campaign_plan = build_test_campaign_plan(
        testing_config,
        completed_stages=completed_stages,
        validity_flags=validity_flags,
        warnings=warnings,
    )
    readiness = build_readiness_summary(
        campaign_plan,
        gate_results,
        completed_stages=completed_stages,
        calibrated_model_state_reference=None if selected_package is None else "updated_model_overrides_from_tests.json",
    )
    destination = write_testing_outputs(
        output_dir,
        campaign_plan=campaign_plan,
        articles=articles,
        instrumentation_plans=instrumentation_plans,
        test_matrix=test_matrix,
        datasets=cleaned_datasets,
        run_summaries=run_summaries,
        comparisons=comparisons,
        calibration_packages=calibration_packages,
        gate_results=gate_results,
        readiness=readiness,
        validity_flags=validity_flags,
        warnings=warnings,
        updated_config=updated_config,
        trace_plot_payloads=_build_trace_plot_payloads(cleaned_datasets, model_source, model_history),
    )
    return {
        "output_dir": destination,
        "campaign_plan": campaign_plan,
        "articles": articles,
        "instrumentation_plans": instrumentation_plans,
        "test_matrix": test_matrix,
        "datasets": cleaned_datasets,
        "run_summaries": run_summaries,
        "comparisons": comparisons,
        "calibration_packages": calibration_packages,
        "selected_calibration_package": selected_package,
        "gate_results": gate_results,
        "readiness": readiness,
        "updated_config": updated_config,
        "validity_flags": validity_flags,
        "warnings": warnings,
    }
