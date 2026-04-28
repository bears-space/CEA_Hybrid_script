"""Recommended point-by-point test matrix generation."""

from __future__ import annotations

from typing import Any, Mapping

from src.testing.test_types import TestArticleDefinition, TestMatrixPoint


def _nominal_ranges(nominal_payload: Mapping[str, Any]) -> tuple[list[float], list[float], float]:
    metrics = nominal_payload.get("metrics", {})
    pc_avg = float(metrics.get("pc_avg_bar", 0.0)) * 1.0e5
    thrust_avg = float(metrics.get("thrust_avg_n", 0.0))
    burn_time = float(metrics.get("burn_time_actual_s", 0.0))
    return (
        [0.85 * pc_avg, 1.15 * pc_avg] if pc_avg > 0.0 else [0.0, 0.0],
        [0.85 * thrust_avg, 1.15 * thrust_avg] if thrust_avg > 0.0 else [0.0, 0.0],
        burn_time,
    )


def build_test_matrix(
    testing_config: Mapping[str, object],
    *,
    articles: list[TestArticleDefinition],
    nominal_payload: Mapping[str, Any],
) -> list[TestMatrixPoint]:
    """Build a simple but explicit campaign matrix for the enabled articles."""

    del testing_config
    pressure_range, thrust_range, nominal_burn_time_s = _nominal_ranges(nominal_payload)
    rows: list[TestMatrixPoint] = []
    for article in articles:
        if article.article_type == "coupon":
            rows.append(
                TestMatrixPoint(
                    point_id=f"{article.article_id}_dimensional_check",
                    article_id=article.article_id,
                    intended_stage=article.stage_name,
                    target_operating_condition="room_temperature_coupon_check",
                    expected_pressure_range=[0.0, 0.0],
                    expected_burn_time_s=None,
                    target_thrust_range=None,
                    objective="Measure density, shrinkage, and repeatability before live-fluid testing.",
                    repeat_group="coupon_repeatability",
                    notes=[],
                )
            )
        elif article.article_type == "coldflow_rig":
            rows.extend(
                [
                    TestMatrixPoint(
                        point_id=f"{article.article_id}_nominal_flow",
                        article_id=article.article_id,
                        intended_stage=article.stage_name,
                        target_operating_condition="nominal_flow",
                        expected_pressure_range=pressure_range,
                        expected_burn_time_s=1.0,
                        target_thrust_range=None,
                        objective="Nominal hydraulic validation point for injector and feed calibration.",
                        repeat_group="coldflow_nominal",
                        notes=[],
                    ),
                    TestMatrixPoint(
                        point_id=f"{article.article_id}_high_flow",
                        article_id=article.article_id,
                        intended_stage=article.stage_name,
                        target_operating_condition="high_flow",
                        expected_pressure_range=[1.1 * pressure_range[0], 1.2 * pressure_range[1]],
                        expected_burn_time_s=1.0,
                        target_thrust_range=None,
                        objective="Bounding higher-flow pressure-drop allocation and injector CdA behavior.",
                        repeat_group=None,
                        notes=[],
                    ),
                    TestMatrixPoint(
                        point_id=f"{article.article_id}_low_flow",
                        article_id=article.article_id,
                        intended_stage=article.stage_name,
                        target_operating_condition="low_flow",
                        expected_pressure_range=[0.7 * pressure_range[0], 0.85 * pressure_range[1]],
                        expected_burn_time_s=1.0,
                        target_thrust_range=None,
                        objective="Bounding lower-flow hydraulic behavior and tap sensitivity.",
                        repeat_group=None,
                        notes=[],
                    ),
                ]
            )
        elif article.stage_name == "subscale_hotfire":
            rows.extend(
                [
                    TestMatrixPoint(
                        point_id=f"{article.article_id}_nominal_hotfire",
                        article_id=article.article_id,
                        intended_stage=article.stage_name,
                        target_operating_condition="nominal_hotfire",
                        expected_pressure_range=[0.8 * pressure_range[0], 0.9 * pressure_range[1]],
                        expected_burn_time_s=article.target_burn_time_s,
                        target_thrust_range=[0.35 * thrust_range[0], 0.65 * thrust_range[1]],
                        objective="Nominal subscale ballistic-learning fire.",
                        repeat_group="subscale_nominal",
                        notes=[],
                    ),
                    TestMatrixPoint(
                        point_id=f"{article.article_id}_short_conservative",
                        article_id=article.article_id,
                        intended_stage=article.stage_name,
                        target_operating_condition="short_duration_conservative",
                        expected_pressure_range=[0.75 * pressure_range[0], 0.85 * pressure_range[1]],
                        expected_burn_time_s=max((article.target_burn_time_s or 0.3) * 0.6, 0.2),
                        target_thrust_range=[0.3 * thrust_range[0], 0.6 * thrust_range[1]],
                        objective="Conservative shorter-duration fire to screen ignition and early-burn issues.",
                        repeat_group=None,
                        notes=[],
                    ),
                ]
            )
        elif article.stage_name == "fullscale_short_duration":
            rows.append(
                TestMatrixPoint(
                    point_id=f"{article.article_id}_startup_screen",
                    article_id=article.article_id,
                    intended_stage=article.stage_name,
                    target_operating_condition="startup_screen",
                    expected_pressure_range=pressure_range,
                    expected_burn_time_s=max((article.target_burn_time_s or nominal_burn_time_s) * 0.8, 0.25),
                    target_thrust_range=thrust_range,
                    objective="Startup and early-burn full-scale development screen.",
                    repeat_group=None,
                    notes=[],
                )
            )
        elif article.stage_name == "fullscale_nominal_duration":
            rows.extend(
                [
                    TestMatrixPoint(
                        point_id=f"{article.article_id}_nominal_duration_1",
                        article_id=article.article_id,
                        intended_stage=article.stage_name,
                        target_operating_condition="nominal_duration",
                        expected_pressure_range=pressure_range,
                        expected_burn_time_s=article.target_burn_time_s or nominal_burn_time_s,
                        target_thrust_range=thrust_range,
                        objective="Primary nominal-duration development run.",
                        repeat_group="fullscale_repeatability",
                        notes=[],
                    ),
                    TestMatrixPoint(
                        point_id=f"{article.article_id}_nominal_duration_2",
                        article_id=article.article_id,
                        intended_stage=article.stage_name,
                        target_operating_condition="nominal_duration_repeat",
                        expected_pressure_range=pressure_range,
                        expected_burn_time_s=article.target_burn_time_s or nominal_burn_time_s,
                        target_thrust_range=thrust_range,
                        objective="Repeatability follow-on run using the same nominal point.",
                        repeat_group="fullscale_repeatability",
                        notes=[],
                    ),
                ]
            )
    return rows
