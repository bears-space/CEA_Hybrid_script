"""Construction of CFD case definitions from targets and reduced-order operating points."""

from __future__ import annotations

from typing import Any, Mapping

from src.cfd.cfd_boundary_conditions import build_cfd_boundary_conditions
from src.cfd.cfd_geometry_export import build_cfd_geometry_package
from src.cfd.cfd_operating_points import select_operating_points_for_target
from src.cfd.cfd_types import CfdCaseDefinition, CfdTargetDefinition
from src.injector_design.injector_types import InjectorGeometryDefinition
from src.nozzle_offdesign.nozzle_offdesign_types import NozzleOffDesignResult
from src.sizing.geometry_types import GeometryDefinition
from src.thermal.thermal_types import ThermalSizingResult


SOLVER_CLASS_BY_CATEGORY = {
    "injector_plenum": "pressure_based_nonreacting",
    "headend_prechamber": "pressure_based_nonreacting",
    "nozzle_local": "compressible_rans",
    "reacting_internal_region": "reacting_rans_placeholder",
}


def _solver_class_for_target(target: CfdTargetDefinition, cfd_config: Mapping[str, Any]) -> str:
    overrides = dict(cfd_config.get("recommended_solver_classes", {}))
    return str(overrides.get(target.target_category, SOLVER_CLASS_BY_CATEGORY.get(target.target_category, "placeholder_solver")))


def build_cfd_case_definitions(
    targets: list[CfdTargetDefinition],
    *,
    cfd_config: Mapping[str, Any],
    geometry: GeometryDefinition,
    nominal_payload: Mapping[str, Any],
    injector_geometry: InjectorGeometryDefinition | None = None,
    corner_payload: Mapping[str, Any] | None = None,
    ballistics_payload: Mapping[str, Any] | None = None,
    nozzle_result: NozzleOffDesignResult | None = None,
    thermal_result: ThermalSizingResult | None = None,
    ingested_case_ids: set[str] | None = None,
    mode: str = "cfd_plan",
) -> tuple[list[CfdCaseDefinition], list[str]]:
    """Build the explicit CFD cases for the ordered campaign targets."""

    warnings: list[str] = []
    case_definitions: list[CfdCaseDefinition] = []
    seen_case_ids: set[str] = set()
    completed_case_ids = set(ingested_case_ids or set())

    for target in targets:
        operating_points, selection_warnings = select_operating_points_for_target(
            target,
            cfd_config=cfd_config,
            geometry=geometry,
            nominal_payload=nominal_payload,
            corner_payload=corner_payload,
            ballistics_payload=ballistics_payload,
            nozzle_result=nozzle_result,
            thermal_result=thermal_result,
        )
        warnings.extend(selection_warnings)
        solver_class = _solver_class_for_target(target, cfd_config)
        for index, operating_point in enumerate(operating_points, start=1):
            base_case_id = f"{target.priority_rank:02d}_{target.target_name}_{operating_point.operating_point_name}"
            case_id = base_case_id
            suffix = 2
            while case_id in seen_case_ids:
                case_id = f"{base_case_id}_{suffix}"
                suffix += 1
            seen_case_ids.add(case_id)

            geometry_package = build_cfd_geometry_package(
                target,
                geometry=geometry,
                injector_geometry=injector_geometry,
                cfd_config=cfd_config,
            )
            boundary_conditions = build_cfd_boundary_conditions(target, operating_point, cfd_config)
            status = "results_ingested" if case_id in completed_case_ids else ("exported" if mode == "cfd_export_cases" else "planned")
            case_definitions.append(
                CfdCaseDefinition(
                    case_id=case_id,
                    target_definition=target,
                    operating_point=operating_point,
                    geometry_package=geometry_package,
                    boundary_conditions=boundary_conditions,
                    recommended_solver_class=solver_class,
                    priority_rank=target.priority_rank,
                    export_paths={
                        "case_definition_json": f"cases/{case_id}.json",
                        "geometry_package_json": f"geometry_packages/{case_id}.json",
                        "boundary_conditions_json": f"boundary_conditions/{case_id}.json",
                    },
                    status=status,
                    notes=[
                        f"Case {index} for target '{target.target_name}'.",
                        "External CFD setup should preserve the geometry scope and operating-point linkage exported here.",
                    ],
                )
            )
    return case_definitions, warnings
