"""Test article definition helpers."""

from __future__ import annotations

from typing import Mapping

from src.injector_design.injector_types import InjectorGeometryDefinition
from src.nozzle_offdesign.nozzle_offdesign_types import NozzleOffDesignResult
from src.sizing.geometry_types import GeometryDefinition
from src.testing.test_types import TestArticleDefinition, TestStageDefinition


def _subscale_burn_time(target_burn_time_s: float, scale_ratio: float) -> float:
    return max(target_burn_time_s * max(scale_ratio, 0.1), 0.1)


def build_test_articles(
    testing_config: Mapping[str, object],
    *,
    stages: list[TestStageDefinition],
    geometry: GeometryDefinition,
    injector_geometry: InjectorGeometryDefinition | None,
    nozzle_result: NozzleOffDesignResult | None,
) -> list[TestArticleDefinition]:
    """Create explicit article definitions for the currently enabled campaign stages."""

    scale_ratio = float(testing_config.get("article_scaling", {}).get("subscale_linear_scale", 0.5))
    nominal_burn_time_s = float(testing_config.get("article_scaling", {}).get("nominal_burn_time_s", 1.0))
    source_geometry_reference = str(testing_config.get("geometry_reference_label", "frozen_geometry"))
    injector_reference = "baseline_equivalent_injector"
    if injector_geometry is not None:
        injector_reference = f"showerhead_{injector_geometry.hole_count}x{injector_geometry.hole_diameter_m * 1000.0:.3f}mm"
    nozzle_reference = "baseline_nozzle"
    if nozzle_result is not None:
        nozzle_reference = str(nozzle_result.recommendations.get("recommended_usage_mode", "baseline_nozzle"))

    articles: list[TestArticleDefinition] = []
    for stage in stages:
        if stage.stage_name == "material_coupon":
            articles.append(
                TestArticleDefinition(
                    article_id="coupon_material_stack_v1",
                    article_scale="coupon",
                    article_type="coupon",
                    source_geometry_reference=source_geometry_reference,
                    stage_name=stage.stage_name,
                    geometric_scaling_notes=["Coupon article for grain material and process checks only."],
                    injector_reference=None,
                    nozzle_reference=None,
                    material_stack_reference="paraffin_abs_10vol",
                    target_burn_time_s=None,
                    target_operating_point_source="manufacturing_process",
                    representative_for_baseline=False,
                    intentional_differences=["No flow path or hot-fire hardware."],
                    notes=["Used to bound manufacturing repeatability before live-fluid tests."],
                )
            )
        elif stage.stage_name == "hydraulic_validation":
            articles.append(
                TestArticleDefinition(
                    article_id="coldflow_rig_v1",
                    article_scale="subscale",
                    article_type="coldflow_rig",
                    source_geometry_reference=source_geometry_reference,
                    stage_name=stage.stage_name,
                    geometric_scaling_notes=["Feed and injector analog for hydraulic validation; chamber and fuel hardware may be omitted."],
                    injector_reference=injector_reference,
                    nozzle_reference=None,
                    material_stack_reference="line_valve_injector_stack",
                    target_burn_time_s=1.0,
                    target_operating_point_source="hydraulic_validation_dataset",
                    representative_for_baseline=True,
                    intentional_differences=["Cold-flow rig may use water or inert surrogate fluid."],
                    notes=["Directly supports feed and injector reduced-order calibration."],
                )
            )
        elif stage.stage_name == "subscale_hotfire":
            articles.append(
                TestArticleDefinition(
                    article_id="subscale_ballistic_v1",
                    article_scale="subscale",
                    article_type="ballistic_subscale",
                    source_geometry_reference=source_geometry_reference,
                    stage_name=stage.stage_name,
                    geometric_scaling_notes=[f"Linear subscale analog with scale ratio {scale_ratio:.3f} relative to the baseline geometry."],
                    injector_reference=injector_reference,
                    nozzle_reference="conservative_ground_test_nozzle" if nozzle_result and not nozzle_result.recommendations.get("ground_test_suitable", True) else nozzle_reference,
                    material_stack_reference="baseline_structural_and_thermal_stack",
                    target_burn_time_s=_subscale_burn_time(nominal_burn_time_s, scale_ratio),
                    target_operating_point_source=str(testing_config.get("test_campaign_source", "nominal_workflow")),
                    representative_for_baseline=False,
                    intentional_differences=["Scaled analog article; full transferability to full scale is not assumed."],
                    notes=["Primary hot-fire learning article for regression and efficiency updates."],
                )
            )
        elif stage.stage_name == "fullscale_short_duration":
            articles.append(
                TestArticleDefinition(
                    article_id="fullscale_dev_short_v1",
                    article_scale="fullscale",
                    article_type="fullscale_dev",
                    source_geometry_reference=source_geometry_reference,
                    stage_name=stage.stage_name,
                    geometric_scaling_notes=["Baseline full-scale development article with conservative early-burn duration limit."],
                    injector_reference=injector_reference,
                    nozzle_reference="conservative_ground_test_nozzle" if nozzle_result and nozzle_result.recommendations.get("recommended_usage_mode") == "baseline_flight_nozzle" else nozzle_reference,
                    material_stack_reference="baseline_structural_and_thermal_stack",
                    target_burn_time_s=max(0.25 * nominal_burn_time_s, 0.25),
                    target_operating_point_source=str(testing_config.get("test_campaign_source", "nominal_workflow")),
                    representative_for_baseline=True,
                    intentional_differences=["Burn duration intentionally truncated for startup and survivability focus."],
                    notes=["Representative hardware for early full-scale development."],
                )
            )
        elif stage.stage_name == "fullscale_nominal_duration":
            articles.append(
                TestArticleDefinition(
                    article_id="fullscale_dev_nominal_v1",
                    article_scale="fullscale",
                    article_type="fullscale_dev",
                    source_geometry_reference=source_geometry_reference,
                    stage_name=stage.stage_name,
                    geometric_scaling_notes=["Baseline full-scale nominal-duration development article."],
                    injector_reference=injector_reference,
                    nozzle_reference=nozzle_reference,
                    material_stack_reference="baseline_structural_and_thermal_stack",
                    target_burn_time_s=nominal_burn_time_s,
                    target_operating_point_source=str(testing_config.get("test_campaign_source", "nominal_workflow")),
                    representative_for_baseline=True,
                    intentional_differences=[],
                    notes=["Nominal-duration repeatability and survivability article."],
                )
            )
    return articles
