"""Testing workflow export, report, and lightweight plotting helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from src.io_utils import write_json
from src.post.csv_export import write_rows_csv
from src.post.plotting import write_grouped_horizontal_bar_chart, write_horizontal_bar_chart, write_line_plot
from src.testing.test_types import (
    HotfireCalibrationPackage,
    InstrumentationPlan,
    ModelVsTestComparison,
    ProgressionGateResult,
    ReadinessSummary,
    TestArticleDefinition,
    TestCampaignPlan,
    TestDataset,
    TestMatrixPoint,
    TestRunSummary,
)


def _stage_rows(plan: TestCampaignPlan) -> list[dict[str, Any]]:
    return [stage.to_dict() for stage in plan.stages]


def _comparison_rows(comparisons: Sequence[ModelVsTestComparison]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for comparison in comparisons:
        row = comparison.to_dict()
        row["pressure_rmse_percent"] = comparison.pressure_trace_error.get("rmse_percent")
        row["thrust_rmse_percent"] = comparison.thrust_trace_error.get("rmse_percent")
        rows.append(row)
    return rows


def _summary_lines(
    plan: TestCampaignPlan,
    readiness: ReadinessSummary,
    run_summaries: Sequence[TestRunSummary],
    comparisons: Sequence[ModelVsTestComparison],
    packages: Sequence[HotfireCalibrationPackage],
    gate_results: Sequence[ProgressionGateResult],
    warnings: Sequence[str],
) -> list[str]:
    active_gate = next((gate for gate in gate_results if gate.stage_name == plan.recommended_next_stage), None)
    return [
        "Testing Campaign Summary",
        f"Campaign valid: {plan.test_progression_valid}",
        f"Recommended next stage: {plan.recommended_next_stage or 'n/a'}",
        f"Recommended next test: {readiness.recommended_next_test or 'n/a'}",
        f"Completed stages: {', '.join(readiness.completed_stages) if readiness.completed_stages else 'none'}",
        f"Run summaries available: {len(run_summaries)}",
        f"Model-vs-test comparisons: {len(comparisons)}",
        f"Hot-fire calibration packages: {len(packages)}",
        f"Outstanding blockers: {', '.join(readiness.outstanding_blockers) if readiness.outstanding_blockers else 'none'}",
        f"Active gate pass: {active_gate.pass_fail if active_gate is not None else 'n/a'}",
        "",
        "Warnings:",
        *(warnings or ["None"]),
    ]


def write_testing_outputs(
    output_dir: str | Path,
    *,
    campaign_plan: TestCampaignPlan,
    articles: Sequence[TestArticleDefinition],
    instrumentation_plans: Sequence[InstrumentationPlan],
    test_matrix: Sequence[TestMatrixPoint],
    datasets: Sequence[TestDataset],
    run_summaries: Sequence[TestRunSummary],
    comparisons: Sequence[ModelVsTestComparison],
    calibration_packages: Sequence[HotfireCalibrationPackage],
    gate_results: Sequence[ProgressionGateResult],
    readiness: ReadinessSummary,
    validity_flags: Mapping[str, bool],
    warnings: Sequence[str],
    updated_config: Mapping[str, Any] | None,
    trace_plot_payloads: Sequence[Mapping[str, Any]] = (),
) -> Path:
    """Write the standard test-progression bundle."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    cleaned_dir = destination / "test_datasets_cleaned"
    cleaned_dir.mkdir(parents=True, exist_ok=True)

    write_json(destination / "test_campaign_plan.json", campaign_plan.to_dict())
    write_rows_csv(destination / "test_stages.csv", _stage_rows(campaign_plan))
    write_json(destination / "test_articles.json", {"articles": [article.to_dict() for article in articles]})
    write_json(destination / "instrumentation_plans.json", {"instrumentation_plans": [plan.to_dict() for plan in instrumentation_plans]})
    write_rows_csv(destination / "test_matrix.csv", [point.to_dict() for point in test_matrix])
    for dataset in datasets:
        write_json(cleaned_dir / f"{dataset.run_id}.json", dataset.to_dict())
    write_rows_csv(destination / "test_run_summaries.csv", [summary.to_dict() for summary in run_summaries])
    write_rows_csv(destination / "model_vs_test_comparisons.csv", _comparison_rows(comparisons))
    write_json(destination / "hotfire_calibration_packages.json", {"packages": [package.to_dict() for package in calibration_packages]})
    write_json(destination / "progression_gates.json", {"gates": [gate.to_dict() for gate in gate_results]})
    write_json(destination / "readiness_summary.json", readiness.to_dict())
    write_json(
        destination / "testing_checks.json",
        {
            "validity_flags": dict(validity_flags),
            "test_progression_valid": campaign_plan.test_progression_valid,
            "warnings": list(warnings),
            "failure_reason": campaign_plan.failure_reason,
        },
    )
    (destination / "testing_summary.txt").write_text(
        "\n".join(_summary_lines(campaign_plan, readiness, run_summaries, comparisons, calibration_packages, gate_results, warnings)) + "\n",
        encoding="utf-8",
    )

    if updated_config is not None:
        write_json(destination / "updated_model_overrides_from_tests.json", dict(updated_config))
    if calibration_packages:
        write_json(
            destination / "calibrated_regression_packages.json",
            {
                "packages": [
                    {
                        "package_name": package.package_name,
                        "source_run_ids": package.source_run_ids,
                        "fitted_regression_parameters": package.fitted_regression_parameters,
                    }
                    for package in calibration_packages
                ]
            },
        )
        write_json(
            destination / "calibrated_efficiency_packages.json",
            {
                "packages": [
                    {
                        "package_name": package.package_name,
                        "source_run_ids": package.source_run_ids,
                        "fitted_cstar_efficiency": package.fitted_cstar_efficiency,
                        "fitted_cf_or_nozzle_loss_correction": package.fitted_cf_or_nozzle_loss_correction,
                    }
                    for package in calibration_packages
                ]
            },
        )

    if campaign_plan.stages:
        write_horizontal_bar_chart(
            destination / "test_campaign_overview.svg",
            [{"label": stage.stage_name, "value": float(stage.stage_order)} for stage in campaign_plan.stages],
            "Ordered Test Campaign",
            "Stage Order [-]",
        )
    if run_summaries:
        write_grouped_horizontal_bar_chart(
            destination / "burn_duration_impulse_comparison.svg",
            [
                {
                    "label": summary.run_id,
                    "values": {
                        "Burn Time [s]": float(summary.achieved_burn_time_s),
                        "Impulse [N s]": float(summary.total_impulse_ns or 0.0),
                    },
                }
                for summary in run_summaries
            ],
            ["Burn Time [s]", "Impulse [N s]"],
            "Burn Duration and Impulse by Test Run",
            "Magnitude",
        )
    if gate_results:
        write_horizontal_bar_chart(
            destination / "progression_gate_status.svg",
            [{"label": gate.stage_name, "value": 1.0 if gate.pass_fail else 0.0} for gate in gate_results],
            "Progression Gate Status",
            "Pass = 1, Fail = 0",
        )
    if calibration_packages:
        write_grouped_horizontal_bar_chart(
            destination / "calibration_update_summary.svg",
            [
                {
                    "label": package.package_name,
                    "values": {
                        "a multiplier": float(package.fitted_regression_parameters.get("a_multiplier", 1.0)),
                        "c* eff": float(package.fitted_cstar_efficiency or 0.0),
                        "nozzle loss": float(package.fitted_cf_or_nozzle_loss_correction or 0.0),
                    },
                }
                for package in calibration_packages
            ],
            ["a multiplier", "c* eff", "nozzle loss"],
            "Calibration Package Summary",
            "Value",
        )
    for trace in trace_plot_payloads:
        write_line_plot(
            destination / f"{trace['filename']}.svg",
            trace["series"],
            trace["title"],
            trace["x_label"],
            trace["y_label"],
        )
    return destination
