"""Current readiness summary construction."""

from __future__ import annotations

from typing import Sequence

from src.testing.test_types import ProgressionGateResult, ReadinessSummary, TestCampaignPlan, TestRunSummary


def determine_completed_stages(
    run_summaries: Sequence[TestRunSummary],
    *,
    hydraulic_calibration_ready: bool,
) -> list[str]:
    """Infer completed stages from ingested runs plus prerequisite calibration state."""

    completed = sorted({summary.stage_name for summary in run_summaries})
    if hydraulic_calibration_ready and "hydraulic_validation" not in completed:
        completed.append("hydraulic_validation")
    return completed


def build_readiness_summary(
    campaign_plan: TestCampaignPlan,
    gate_results: Sequence[ProgressionGateResult],
    *,
    completed_stages: list[str],
    calibrated_model_state_reference: str | None,
) -> ReadinessSummary:
    """Build the top-level readiness summary for the next recommended test."""

    next_stage = campaign_plan.recommended_next_stage
    stage_gate = next((gate for gate in gate_results if gate.stage_name == next_stage), None)
    blockers = [] if stage_gate is None else list(stage_gate.blocking_issues)
    current_stage = None if not completed_stages else max(completed_stages, key=lambda name: next((stage.stage_order for stage in campaign_plan.stages if stage.stage_name == name), -1))
    overall_ready = True if stage_gate is None else bool(stage_gate.pass_fail)
    return ReadinessSummary(
        current_stage=current_stage,
        completed_stages=list(completed_stages),
        outstanding_blockers=blockers,
        recommended_next_test=campaign_plan.recommended_next_test,
        calibrated_model_state_reference=calibrated_model_state_reference,
        overall_readiness_flag=overall_ready,
        notes=[
            "Readiness is based on explicit gates and currently ingested datasets only.",
            "Absence of data does not imply readiness; missing-data blockers are surfaced directly in the gate results.",
        ],
    )
