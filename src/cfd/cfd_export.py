"""CFD campaign planning output export, reports, and simple plots."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from src.cfd.cfd_types import CfdCampaignPlan, CfdCaseDefinition, CfdCorrectionPackage, CfdResultSummary
from src.io_utils import write_json
from src.post.csv_export import write_rows_csv
from src.post.plotting import write_grouped_horizontal_bar_chart, write_horizontal_bar_chart, write_scatter_plot


def _summary_lines(
    plan: CfdCampaignPlan,
    case_definitions: Sequence[CfdCaseDefinition],
    correction_packages: Sequence[CfdCorrectionPackage],
    result_summaries: Sequence[CfdResultSummary],
) -> list[str]:
    warnings = plan.warnings or ["None"]
    ordered_targets = [f"{target.priority_rank}. {target.target_name}" for target in plan.targets]
    return [
        "CFD Campaign Summary",
        f"Plan valid: {plan.cfd_plan_valid}",
        f"Case source: {plan.case_source}",
        f"Corrections source: {plan.corrections_source}",
        f"Ordered campaign: {', '.join(ordered_targets)}",
        f"Recommended next CFD case: {plan.recommended_next_case_id or 'n/a'}",
        f"Case definitions exported: {len(case_definitions)}",
        f"Ingested result summaries: {len(result_summaries)}",
        f"Reusable correction packages: {len(correction_packages)}",
        "",
        "Warnings:",
        *warnings,
    ]


def _target_rows(plan: CfdCampaignPlan) -> list[dict[str, Any]]:
    return [
        {
            "priority_rank": target.priority_rank,
            "target_name": target.target_name,
            "target_category": target.target_category,
            "objective_description": target.objective_description,
            "required_geometry_scope": target.required_geometry_scope,
            "recommended_fidelity": target.recommended_fidelity,
            "recommended_flow_type": target.recommended_flow_type,
            "downstream_models_affected": "; ".join(target.downstream_models_affected),
        }
        for target in plan.targets
    ]


def _operating_point_rows(case_definitions: Sequence[CfdCaseDefinition]) -> list[dict[str, Any]]:
    rows = []
    for case in case_definitions:
        point = case.operating_point
        rows.append(
            {
                "case_id": case.case_id,
                "target_name": case.target_definition.target_name,
                "operating_point_name": point.operating_point_name,
                "source_stage": point.source_stage,
                "time_s": point.time_s,
                "chamber_pressure_pa": point.chamber_pressure_pa,
                "injector_inlet_pressure_pa": point.injector_inlet_pressure_pa,
                "mass_flow_kg_s": point.mass_flow_kg_s,
                "oxidizer_mass_flow_kg_s": point.oxidizer_mass_flow_kg_s,
                "fuel_mass_flow_kg_s": point.fuel_mass_flow_kg_s,
                "ambient_pressure_pa": point.ambient_pressure_pa,
                "fluid_properties_reference": point.fluid_properties_reference,
            }
        )
    return rows


def write_cfd_outputs(
    output_dir: str | Path,
    *,
    plan: CfdCampaignPlan,
    case_definitions: Sequence[CfdCaseDefinition],
    correction_packages: Sequence[CfdCorrectionPackage],
    result_summaries: Sequence[CfdResultSummary],
    comparison_rows: Sequence[dict[str, Any]],
    updated_config: dict[str, Any] | None,
) -> Path:
    """Write the standard CFD planning and correction bundle."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    cases_dir = destination / "cases"
    geometry_dir = destination / "geometry_packages"
    bc_dir = destination / "boundary_conditions"
    cases_dir.mkdir(parents=True, exist_ok=True)
    geometry_dir.mkdir(parents=True, exist_ok=True)
    bc_dir.mkdir(parents=True, exist_ok=True)

    for case in case_definitions:
        write_json(cases_dir / f"{case.case_id}.json", case.to_dict())
        write_json(geometry_dir / f"{case.case_id}.json", case.geometry_package.to_dict())
        write_json(bc_dir / f"{case.case_id}.json", case.boundary_conditions.to_dict())

    write_json(destination / "cfd_campaign_plan.json", plan.to_dict())
    write_rows_csv(destination / "cfd_targets.csv", _target_rows(plan))
    write_json(destination / "cfd_case_definitions.json", {"case_definitions": [case.to_dict() for case in case_definitions]})
    write_json(destination / "cfd_geometry_packages.json", {"geometry_packages": [case.geometry_package.to_dict() for case in case_definitions]})
    write_json(destination / "cfd_boundary_conditions.json", {"boundary_conditions": [case.boundary_conditions.to_dict() for case in case_definitions]})
    write_rows_csv(destination / "cfd_operating_points.csv", _operating_point_rows(case_definitions))
    write_json(destination / "cfd_corrections.json", {"correction_packages": [package.to_dict() for package in correction_packages]})
    write_json(
        destination / "cfd_checks.json",
        {
            "validity_flags": plan.validity_flags,
            "cfd_plan_valid": plan.cfd_plan_valid,
            "warnings": plan.warnings,
            "failure_reason": plan.failure_reason,
        },
    )
    (destination / "cfd_summary.txt").write_text(
        "\n".join(_summary_lines(plan, case_definitions, correction_packages, result_summaries)) + "\n",
        encoding="utf-8",
    )

    if result_summaries:
        write_json(destination / "cfd_result_summaries.json", {"result_summaries": [summary.to_dict() for summary in result_summaries]})
    if comparison_rows:
        write_rows_csv(destination / "cfd_vs_reduced_order_comparison.csv", comparison_rows)
    if updated_config is not None:
        write_json(destination / "updated_model_overrides.json", updated_config)
        write_json(destination / "updated_correction_packages.json", {"correction_packages": [package.to_dict() for package in correction_packages]})

    if plan.targets:
        write_horizontal_bar_chart(
            destination / "cfd_campaign_priority.svg",
            [
                {
                    "label": target.target_name,
                    "value": float(target.priority_rank),
                }
                for target in plan.targets
            ],
            "CFD Campaign Priority Rank (lower is earlier)",
            "Priority Rank [-]",
        )

        affected_modules = sorted({module for target in plan.targets for module in target.downstream_models_affected})
        if affected_modules:
            write_grouped_horizontal_bar_chart(
                destination / "cfd_target_module_matrix.svg",
                [
                    {
                        "label": target.target_name,
                        "values": {
                            module: (1.0 if module in target.downstream_models_affected else 0.0)
                            for module in affected_modules
                        },
                    }
                    for target in plan.targets
                ],
                affected_modules,
                "CFD Target vs Affected Module Matrix",
                "Membership",
            )

    selected_points = [
        case.operating_point
        for case in case_definitions
        if case.operating_point.time_s is not None and case.operating_point.chamber_pressure_pa is not None
    ]
    if selected_points:
        write_scatter_plot(
            destination / "cfd_operating_points_over_burn.svg",
            [
                {
                    "label": target.target_name,
                    "x": [
                        case.operating_point.time_s
                        for case in case_definitions
                        if case.target_definition.target_name == target.target_name and case.operating_point.time_s is not None
                    ],
                    "y": [
                        case.operating_point.chamber_pressure_pa / 1.0e5
                        for case in case_definitions
                        if case.target_definition.target_name == target.target_name
                        and case.operating_point.time_s is not None
                        and case.operating_point.chamber_pressure_pa is not None
                    ],
                }
                for target in plan.targets
            ],
            "Selected CFD Operating Points Over Burn History",
            "Time [s]",
            "Chamber Pressure [bar]",
        )

    if comparison_rows:
        write_grouped_horizontal_bar_chart(
            destination / "cfd_before_after_corrections.svg",
            [
                {
                    "label": row["parameter"],
                    "values": {
                        "Base": row["base_value"],
                        "Corrected": row["corrected_value"],
                    },
                }
                for row in comparison_rows
            ],
            ["Base", "Corrected"],
            "Reduced-Order Parameters Before vs After CFD Corrections",
            "Value",
        )

    return destination
