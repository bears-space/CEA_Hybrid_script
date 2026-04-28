"""Ordered CFD target generation and default campaign logic."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from src.cfd.cfd_types import CfdTargetDefinition


DEFAULT_TARGET_ORDER = [
    "injector_plenum_plate_flow",
    "headend_prechamber_distribution",
    "nozzle_local_offdesign",
    "reacting_internal_region_refinement",
]


TARGET_TEMPLATES: dict[str, dict[str, Any]] = {
    "injector_plenum_plate_flow": {
        "target_category": "injector_plenum",
        "objective_description": (
            "Resolve plenum maldistribution, injector-hole inflow nonuniformity, and effective loss behavior for the showerhead plate."
        ),
        "why_reduced_order_is_insufficient": (
            "The current reduced-order injector model collapses a real 3D plenum and multi-hole discharge pattern into one equivalent CdA."
        ),
        "required_geometry_scope": "injector_plenum_plate_short_downstream",
        "required_operating_points": [
            "nominal_initial",
            "nominal_average",
            "peak_injector_dp",
            "hot_corner_peak_pc",
            "cold_corner_peak_pc",
        ],
        "recommended_fidelity": "3D steady or quasi-steady RANS cold-flow / nonreacting",
        "recommended_flow_type": "cold_flow",
        "expected_outputs": [
            "effective injector pressure-loss correction",
            "jet-to-jet flow split or maldistribution metric",
            "per-hole or per-ring discharge trends",
            "head-end asymmetry warning indicators",
        ],
        "downstream_models_affected": [
            "injector_design",
            "hydraulic_validation",
            "simulation_0d",
            "simulation_1d",
        ],
        "notes": [
            "Default Stage 1 target.",
            "This target should normally precede head-end or reacting internal CFD.",
        ],
    },
    "headend_prechamber_distribution": {
        "target_category": "headend_prechamber",
        "objective_description": (
            "Resolve showerhead discharge interaction with the prechamber and grain entrance, including recirculation and oxidizer-loading nonuniformity."
        ),
        "why_reduced_order_is_insufficient": (
            "The current quasi-1D model uses a configurable axial bias but cannot predict 3D recirculation, local impingement, or head-end hot-spot drivers."
        ),
        "required_geometry_scope": "injector_face_prechamber_grain_entrance",
        "required_operating_points": [
            "nominal_initial",
            "peak_oxidizer_flow",
            "peak_pc",
            "hot_corner_peak_pc",
        ],
        "recommended_fidelity": "3D nonreacting first; reacting only if later justified",
        "recommended_flow_type": "nonreacting",
        "expected_outputs": [
            "head-end maldistribution factor",
            "grain-entrance oxidizer loading bias",
            "local recirculation or impingement regions",
            "injector-face heat-flux multiplier placeholder",
        ],
        "downstream_models_affected": [
            "simulation_1d",
            "thermal",
        ],
        "notes": [
            "Default Stage 2 target.",
            "Run this only after the injector-plenum question is bounded well enough.",
        ],
    },
    "nozzle_local_offdesign": {
        "target_category": "nozzle_local",
        "objective_description": (
            "Refine severe off-design nozzle behavior, throat/divergence local loading, and likely separation-loss penalties."
        ),
        "why_reduced_order_is_insufficient": (
            "The current nozzle layer uses reduced-order exit-pressure and separation heuristics and cannot predict local separated-flow structure or heat-flux concentration."
        ),
        "required_geometry_scope": "converging_throat_diverging_region",
        "required_operating_points": [
            "worst_ground_overexpansion",
            "startup_ground_case",
            "shutdown_ground_case",
            "matched_altitude_case",
        ],
        "recommended_fidelity": "Axisymmetric or 3D compressible RANS, off-design focused",
        "recommended_flow_type": "compressible",
        "expected_outputs": [
            "nozzle loss factor",
            "separation penalty factor",
            "local throat or divergence heat-flux multiplier",
            "improved off-design risk notes",
        ],
        "downstream_models_affected": [
            "nozzle_offdesign",
            "thermal",
            "simulation_0d",
        ],
        "notes": [
            "Default Stage 3 target.",
            "Only run if the reduced-order nozzle and thermal checks indicate the local nozzle question matters.",
        ],
    },
    "reacting_internal_region_refinement": {
        "target_category": "reacting_internal_region",
        "objective_description": (
            "Refine the coupled internal-flow picture only after lower-order geometry, hydraulic, thermal, and nozzle uncertainties are reduced."
        ),
        "why_reduced_order_is_insufficient": (
            "This target addresses coupled local reacting phenomena that remain after the reduced-order backbone and earlier CFD questions have been narrowed."
        ),
        "required_geometry_scope": "prechamber_grain_port_nozzle_segment",
        "required_operating_points": [
            "peak_pc",
            "nominal_average",
            "hot_corner_peak_pc",
        ],
        "recommended_fidelity": "Reacting RANS or higher-fidelity local campaign",
        "recommended_flow_type": "reacting",
        "expected_outputs": [
            "regression correction map placeholder",
            "local heat-flux map reductions",
            "head-end and port nonuniformity refinement",
            "late-stage reduced-order model update candidates",
        ],
        "downstream_models_affected": [
            "simulation_1d",
            "thermal",
            "future_hotfire_bridge",
        ],
        "notes": [
            "Default Stage 4 target.",
            "This should remain a later campaign item, not the first CFD activity.",
        ],
    },
}


def build_cfd_targets(cfd_config: Mapping[str, Any]) -> tuple[list[CfdTargetDefinition], list[str]]:
    """Build the explicit ordered CFD target list for the current campaign."""

    settings = dict(cfd_config)
    enabled_targets = [str(item) for item in settings.get("enabled_targets", DEFAULT_TARGET_ORDER)]
    priority_order = [str(item) for item in settings.get("target_priority_order", DEFAULT_TARGET_ORDER)]
    warnings: list[str] = []
    ordered_names: list[str] = []

    for target_name in priority_order:
        if target_name in enabled_targets and target_name in TARGET_TEMPLATES and target_name not in ordered_names:
            ordered_names.append(target_name)
    for target_name in enabled_targets:
        if target_name not in TARGET_TEMPLATES:
            warnings.append(f"Unknown CFD target '{target_name}' was ignored.")
            continue
        if target_name not in ordered_names:
            ordered_names.append(target_name)

    if ordered_names != DEFAULT_TARGET_ORDER[: len(ordered_names)]:
        warnings.append(
            "Configured CFD target order deviates from the default recommendation; verify that injector and head-end questions are still being answered before broader CFD."
        )

    targets: list[CfdTargetDefinition] = []
    for index, target_name in enumerate(ordered_names, start=1):
        template = deepcopy(TARGET_TEMPLATES[target_name])
        targets.append(
            CfdTargetDefinition(
                target_name=target_name,
                target_category=str(template["target_category"]),
                priority_rank=index,
                objective_description=str(template["objective_description"]),
                why_reduced_order_is_insufficient=str(template["why_reduced_order_is_insufficient"]),
                required_geometry_scope=str(template["required_geometry_scope"]),
                required_operating_points=[str(item) for item in template["required_operating_points"]],
                recommended_fidelity=str(template["recommended_fidelity"]),
                recommended_flow_type=str(template["recommended_flow_type"]),
                expected_outputs=[str(item) for item in template["expected_outputs"]],
                downstream_models_affected=[str(item) for item in template["downstream_models_affected"]],
                notes=[str(item) for item in template.get("notes", [])],
            )
        )
    return targets, warnings
