"""Ordered test-campaign stage generation."""

from __future__ import annotations

from typing import Mapping

from src.testing.test_types import TestCampaignPlan, TestStageDefinition


def _default_stage_catalog() -> dict[str, TestStageDefinition]:
    return {
        "material_coupon": TestStageDefinition(
            stage_name="material_coupon",
            stage_order=0,
            stage_category="material_coupon",
            objective_description="Verify grain manufacturing repeatability, density, void tendency, and process consistency before fluid or hot-fire work.",
            required_predecessors=[],
            key_questions_to_answer=[
                "Is the paraffin plus ABS grain process repeatable enough to build representative articles?",
                "Do coupon measurements reveal density or shrinkage issues that would undermine later test articles?",
            ],
            success_metrics=["coupon_density_within_limit", "manufacturing_repeatability_acceptably_bounded"],
            required_measurements=["coupon_mass", "coupon_dimensions", "material_density"],
            recommended_article_types=["coupon"],
            notes=["Stage 0 recommendation only; this layer does not replace detailed manufacturing QA documentation."],
        ),
        "hydraulic_validation": TestStageDefinition(
            stage_name="hydraulic_validation",
            stage_order=1,
            stage_category="cold_flow",
            objective_description="Bound feed losses, injector CdA, and pressure-drop allocation before hot-fire model calibration.",
            required_predecessors=["material_coupon"],
            key_questions_to_answer=[
                "Is the reduced-order feed and injector model hydraulically bounded by data?",
                "Are injector inlet and pressure-drop budgets credible enough for hot-fire prediction?",
            ],
            success_metrics=["mdot_rmse_within_limit", "calibration_valid"],
            required_measurements=[
                "upstream_pressure_pa",
                "injector_inlet_pressure_pa",
                "downstream_pressure_pa",
                "mass_flow_kg_s",
                "fluid_temperature_k",
            ],
            recommended_article_types=["coldflow_rig"],
            notes=["This stage integrates the existing hydraulic validation capability into the broader campaign logic."],
        ),
        "subscale_hotfire": TestStageDefinition(
            stage_name="subscale_hotfire",
            stage_order=2,
            stage_category="subscale_hotfire",
            objective_description="Learn regression, c* efficiency, ignition behavior, and gross thermal/model bias cheaply before full-scale development.",
            required_predecessors=["hydraulic_validation"],
            key_questions_to_answer=[
                "Does the reduced-order model capture pressure trace shape and thrust level within configured limits?",
                "What hot-fire calibration updates are needed for regression and efficiency assumptions?",
            ],
            success_metrics=["pressure_trace_error_within_limit", "thrust_trace_error_within_limit", "thermal_red_flags_absent"],
            required_measurements=[
                "chamber_pressure_pa",
                "tank_pressure_pa",
                "thrust_n",
                "ignition_signal",
                "burn_window",
            ],
            recommended_article_types=["ballistic_subscale"],
            notes=["Stage 2 should remain cheap and fast enough to iterate before committing to full-scale hardware."],
        ),
        "fullscale_short_duration": TestStageDefinition(
            stage_name="fullscale_short_duration",
            stage_order=3,
            stage_category="fullscale_short_duration",
            objective_description="Verify startup, early-burn feed realism, and gross structural and thermal survivability on representative hardware.",
            required_predecessors=["subscale_hotfire"],
            key_questions_to_answer=[
                "Are startup and early-burn traces consistent with the updated reduced-order model?",
                "Do structural, thermal, or nozzle concerns appear worse than predicted?",
            ],
            success_metrics=["startup_behavior_acceptable", "pressure_trace_error_within_limit", "no_blocking_survivability_issue"],
            required_measurements=[
                "chamber_pressure_pa",
                "tank_pressure_pa",
                "thrust_n",
                "valve_state",
                "ignition_signal",
            ],
            recommended_article_types=["fullscale_dev"],
            notes=["Stage 3 is an early representative development fire, not a qualification test."],
        ),
        "fullscale_nominal_duration": TestStageDefinition(
            stage_name="fullscale_nominal_duration",
            stage_order=4,
            stage_category="fullscale_nominal_duration",
            objective_description="Verify nominal burn duration, repeatability, total impulse, and end-of-burn behavior on the baseline development article.",
            required_predecessors=["fullscale_short_duration"],
            key_questions_to_answer=[
                "Can the full-scale article run to nominal duration without contradicting structural or thermal predictions?",
                "Is repeatability good enough to justify later qualification logic?",
            ],
            success_metrics=["burn_duration_within_limit", "impulse_error_within_limit", "repeatability_within_limit"],
            required_measurements=[
                "chamber_pressure_pa",
                "tank_pressure_pa",
                "thrust_n",
                "ignition_signal",
                "thermal_indicator_channels",
            ],
            recommended_article_types=["fullscale_dev"],
            notes=["Stage 4 remains a development readiness gate, not final qualification or operations logic."],
        ),
    }


def build_test_stages(testing_config: Mapping[str, object]) -> list[TestStageDefinition]:
    """Build the ordered stage list after applying enabled-stage and ordering settings."""

    catalog = _default_stage_catalog()
    enabled = [str(item) for item in testing_config.get("enabled_stages", catalog.keys())]
    ordered_names = [str(item) for item in testing_config.get("stage_order", enabled)]
    ordered_names = [name for name in ordered_names if name in enabled]
    for name in enabled:
        if name not in ordered_names:
            ordered_names.append(name)
    return [
        TestStageDefinition(
            stage_name=catalog[name].stage_name,
            stage_order=index,
            stage_category=catalog[name].stage_category,
            objective_description=catalog[name].objective_description,
            required_predecessors=[pred for pred in catalog[name].required_predecessors if pred in ordered_names],
            key_questions_to_answer=list(catalog[name].key_questions_to_answer),
            success_metrics=list(catalog[name].success_metrics),
            required_measurements=list(catalog[name].required_measurements),
            recommended_article_types=list(catalog[name].recommended_article_types),
            notes=list(catalog[name].notes),
        )
        for index, name in enumerate(ordered_names)
    ]


def build_test_campaign_plan(
    testing_config: Mapping[str, object],
    *,
    completed_stages: list[str],
    validity_flags: dict[str, bool],
    warnings: list[str],
) -> TestCampaignPlan:
    """Build the top-level campaign plan and identify the next recommended stage."""

    stages = build_test_stages(testing_config)
    recommended_next_stage = next((stage.stage_name for stage in stages if stage.stage_name not in completed_stages), None)
    uncertainty_focus = {
        "material_coupon": ["grain manufacturing repeatability", "material density consistency"],
        "hydraulic_validation": ["feed loss uncertainty", "injector CdA uncertainty"],
        "subscale_hotfire": ["regression-law uncertainty", "cstar efficiency uncertainty", "ignition uncertainty"],
        "fullscale_short_duration": ["startup realism", "early-burn structural and thermal realism"],
        "fullscale_nominal_duration": ["full-duration survivability", "repeatability", "end-of-burn realism"],
    }
    return TestCampaignPlan(
        campaign_name="default_engine_test_campaign",
        campaign_source=str(testing_config.get("test_campaign_source", "nominal_workflow")),
        stages=stages,
        recommended_next_stage=recommended_next_stage,
        recommended_next_test=None if recommended_next_stage is None else f"{recommended_next_stage}_nominal_point",
        uncertainty_focus=list(uncertainty_focus.get(recommended_next_stage or "", [])),
        validity_flags=dict(validity_flags),
        test_progression_valid=all(validity_flags.values()),
        warnings=list(warnings),
        failure_reason=None if all(validity_flags.values()) else "One or more test-campaign setup checks failed.",
        notes=[
            "Testing remains a structured feedback and calibration loop; it does not replace the reduced-order workflow backbone.",
            "Campaign order defaults to coupon, then cold flow, then subscale hot-fire, then full-scale short duration, then full-scale nominal duration.",
        ],
    )
