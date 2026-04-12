"""Reduced-order hydraulic prediction for Step 5 cold-flow validation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from blowdown_hybrid.hydraulics import feed_pressure_drop_pa
from blowdown_hybrid.models import FeedConfig, InjectorConfig

from src.coldflow.coldflow_types import ColdFlowDataset, ColdFlowPoint, HydraulicPrediction
from src.coldflow.surrogate_fluid import resolve_point_density_kg_m3, resolve_point_fluid_name
from src.simulation.solver_0d import prepare_runtime_case


@dataclass(frozen=True)
class HydraulicModelContext:
    """Resolved reduced-order model inputs used for cold-flow prediction."""

    model_source: str
    base_model_source: str
    test_mode: str
    feed_model_enabled: bool
    feed_config: FeedConfig
    injector_config: InjectorConfig
    injector_geometry_reference: str | None
    design_reference: dict[str, float]


def injector_effective_cda_m2(injector_config: InjectorConfig) -> float:
    return float(injector_config.cd) * float(injector_config.total_area_m2)


def injector_delta_p_from_mdot(mdot_kg_s: float, rho_kg_m3: float, injector_config: InjectorConfig) -> float:
    effective_cda_m2 = injector_effective_cda_m2(injector_config)
    if mdot_kg_s <= 0.0 or rho_kg_m3 <= 0.0 or effective_cda_m2 <= 0.0:
        return 0.0
    return (float(mdot_kg_s) / effective_cda_m2) ** 2 / (2.0 * float(rho_kg_m3))


def _injector_mdot_from_delta_p(delta_p_pa: float, rho_kg_m3: float, injector_config: InjectorConfig) -> float:
    if delta_p_pa <= 0.0 or rho_kg_m3 <= 0.0:
        return 0.0
    return injector_effective_cda_m2(injector_config) * (2.0 * float(rho_kg_m3) * float(delta_p_pa)) ** 0.5


def _predict_total_delta_p_pa(
    mdot_kg_s: float,
    rho_kg_m3: float,
    feed_config: FeedConfig,
    injector_config: InjectorConfig,
    *,
    include_feed_model: bool,
) -> float:
    feed_delta_p_pa = feed_pressure_drop_pa(mdot_kg_s, rho_kg_m3, feed_config) if include_feed_model else 0.0
    return feed_delta_p_pa + injector_delta_p_from_mdot(mdot_kg_s, rho_kg_m3, injector_config)


def _solve_mass_flow_from_available_delta_p(
    available_delta_p_pa: float,
    rho_kg_m3: float,
    feed_config: FeedConfig,
    injector_config: InjectorConfig,
    *,
    include_feed_model: bool,
    mdot_hint_kg_s: float,
) -> float:
    if available_delta_p_pa <= 0.0:
        return 0.0

    lower = 0.0
    upper = max(float(mdot_hint_kg_s), 1.0e-5)
    while _predict_total_delta_p_pa(
        upper,
        rho_kg_m3,
        feed_config,
        injector_config,
        include_feed_model=include_feed_model,
    ) < available_delta_p_pa:
        upper *= 2.0
        if upper > 1.0e3:
            break

    for _ in range(80):
        midpoint = 0.5 * (lower + upper)
        predicted_delta_p_pa = _predict_total_delta_p_pa(
            midpoint,
            rho_kg_m3,
            feed_config,
            injector_config,
            include_feed_model=include_feed_model,
        )
        if predicted_delta_p_pa > available_delta_p_pa:
            upper = midpoint
        else:
            lower = midpoint
    return 0.5 * (lower + upper)


def _context_feed_override(base_feed_config: FeedConfig, coldflow_config: Mapping[str, Any]) -> FeedConfig:
    override = dict(coldflow_config.get("rig", {}).get("feed_model_override", {}))
    if not override:
        return base_feed_config
    feed_kwargs: dict[str, Any] = {}
    for field_name in (
        "line_id_m",
        "line_length_m",
        "friction_factor",
        "minor_loss_k_total",
        "loss_model",
        "pressure_drop_multiplier",
        "manual_delta_p_pa",
    ):
        if override.get(field_name) is not None:
            feed_kwargs[field_name] = (
                float(override[field_name]) if field_name != "loss_model" else str(override[field_name])
            )
    return replace(base_feed_config, **feed_kwargs)


def build_prediction_context(study_config: Mapping[str, Any], coldflow_config: Mapping[str, Any]) -> HydraulicModelContext:
    """Resolve the feed and injector reduced-order model used for cold-flow predictions."""

    injector_model_source = str(coldflow_config.get("injector_model_source", "solver_default")).lower()
    injector_source_override = None if injector_model_source == "solver_default" else injector_model_source
    prepared = prepare_runtime_case(
        study_config,
        injector_source_override=injector_source_override,
    )
    runtime = prepared["runtime"]
    feed_config = _context_feed_override(runtime["feed"], coldflow_config)
    test_mode = str(coldflow_config.get("test_mode", "feed_plus_injector_rig")).lower()
    feed_model_enabled = test_mode != "injector_only_bench"
    if bool(coldflow_config.get("force_disable_feed_model", False)):
        feed_model_enabled = False
    injector_geometry_reference = None
    if runtime.get("injector_geometry") is not None:
        injector_geometry_reference = str(runtime["injector_geometry"].requirement_source)
    elif coldflow_config.get("injector_geometry_path"):
        injector_geometry_reference = str(coldflow_config["injector_geometry_path"])
    return HydraulicModelContext(
        model_source=str(coldflow_config.get("hydraulic_source", "nominal_uncalibrated")),
        base_model_source=str(runtime["derived"].get("injector_source", "equivalent_manual")),
        test_mode=test_mode,
        feed_model_enabled=feed_model_enabled,
        feed_config=feed_config,
        injector_config=runtime["injector"],
        injector_geometry_reference=injector_geometry_reference,
        design_reference={
            "target_mdot_ox_kg_s": float(runtime["derived"]["target_mdot_ox_kg_s"]),
            "design_feed_delta_p_pa": float(runtime["derived"]["design_feed_pressure_drop_bar"]) * 1.0e5,
            "design_injector_delta_p_pa": float(runtime["derived"]["design_injector_delta_p_bar"]) * 1.0e5,
            "design_injector_inlet_pressure_pa": float(runtime["derived"]["design_injector_inlet_pressure_bar"]) * 1.0e5,
            "design_tank_pressure_pa": float(runtime["derived"]["design_tank_pressure_bar"]) * 1.0e5,
        },
    )


def apply_parameter_updates_to_context(
    context: HydraulicModelContext,
    parameter_updates: Mapping[str, Any],
    *,
    hydraulic_source: str,
) -> HydraulicModelContext:
    """Return a new prediction context with calibrated feed and injector parameters applied."""

    feed_config = context.feed_config
    injector_config = context.injector_config
    if parameter_updates.get("feed_pressure_drop_multiplier_calibrated") is not None:
        feed_config = replace(
            feed_config,
            pressure_drop_multiplier=float(parameter_updates["feed_pressure_drop_multiplier_calibrated"]),
        )
    elif parameter_updates.get("feed_loss_multiplier") is not None:
        feed_config = replace(
            feed_config,
            pressure_drop_multiplier=float(feed_config.pressure_drop_multiplier)
            * float(parameter_updates["feed_loss_multiplier"]),
        )

    if hydraulic_source == "geometry_plus_coldflow":
        injector_multiplier = parameter_updates.get(
            "geometry_backcalc_correction_factor",
            parameter_updates.get("injector_cda_multiplier"),
        )
    else:
        injector_multiplier = parameter_updates.get("injector_cda_multiplier")
    if injector_multiplier is not None:
        injector_config = replace(
            injector_config,
            cd=float(injector_config.cd) * float(injector_multiplier),
        )
    elif parameter_updates.get("injector_cd_calibrated") is not None:
        injector_config = replace(
            injector_config,
            cd=float(parameter_updates["injector_cd_calibrated"]),
        )

    return HydraulicModelContext(
        model_source=hydraulic_source,
        base_model_source=context.base_model_source,
        test_mode=context.test_mode,
        feed_model_enabled=context.feed_model_enabled,
        feed_config=feed_config,
        injector_config=injector_config,
        injector_geometry_reference=context.injector_geometry_reference,
        design_reference=dict(context.design_reference),
    )


def predict_point(point: ColdFlowPoint, context: HydraulicModelContext, coldflow_config: Mapping[str, Any]) -> HydraulicPrediction:
    """Predict one cold-flow point using the current reduced-order hydraulic model."""

    fluid_density_kg_m3 = resolve_point_density_kg_m3(point, coldflow_config)
    fluid_name = resolve_point_fluid_name(point, coldflow_config)
    downstream_pressure_pa = float(point.downstream_pressure_pa or 0.0)
    notes: list[str] = []

    if context.feed_model_enabled and point.upstream_pressure_pa is not None:
        available_delta_p_pa = float(point.upstream_pressure_pa) - downstream_pressure_pa
        predicted_mdot_kg_s = _solve_mass_flow_from_available_delta_p(
            available_delta_p_pa,
            fluid_density_kg_m3,
            context.feed_config,
            context.injector_config,
            include_feed_model=True,
            mdot_hint_kg_s=float(point.measured_mdot_kg_s or context.design_reference["target_mdot_ox_kg_s"]),
        )
        pressure_solution_source = "system_solved_from_upstream_and_downstream"
        predicted_feed_delta_p_pa = feed_pressure_drop_pa(
            predicted_mdot_kg_s,
            fluid_density_kg_m3,
            context.feed_config,
        )
        predicted_injector_inlet_pressure_pa = float(point.upstream_pressure_pa) - predicted_feed_delta_p_pa
    else:
        injector_inlet_pressure_pa = (
            float(point.injector_inlet_pressure_pa)
            if point.injector_inlet_pressure_pa is not None
            else float(point.upstream_pressure_pa or downstream_pressure_pa)
        )
        predicted_feed_delta_p_pa = 0.0
        predicted_injector_inlet_pressure_pa = injector_inlet_pressure_pa
        predicted_mdot_kg_s = _injector_mdot_from_delta_p(
            injector_inlet_pressure_pa - downstream_pressure_pa,
            fluid_density_kg_m3,
            context.injector_config,
        )
        pressure_solution_source = "injector_only_from_tapped_inlet_pressure"
        if not context.feed_model_enabled:
            notes.append("Feed loss model disabled for injector-only cold-flow prediction.")

    predicted_injector_delta_p_pa = max(predicted_injector_inlet_pressure_pa - downstream_pressure_pa, 0.0)
    predicted_total_area_m2 = float(context.injector_config.total_area_m2)
    predicted_per_hole_velocity_m_s = 0.0
    if fluid_density_kg_m3 > 0.0 and predicted_total_area_m2 > 0.0:
        predicted_per_hole_velocity_m_s = predicted_mdot_kg_s / (fluid_density_kg_m3 * predicted_total_area_m2)

    return HydraulicPrediction(
        test_id=point.test_id,
        point_index=point.point_index,
        model_source=context.model_source,
        fluid_name=fluid_name,
        fluid_density_kg_m3=float(fluid_density_kg_m3),
        predicted_mdot_kg_s=float(predicted_mdot_kg_s),
        predicted_feed_delta_p_pa=float(predicted_feed_delta_p_pa),
        predicted_injector_delta_p_pa=float(predicted_injector_delta_p_pa),
        predicted_injector_inlet_pressure_pa=float(predicted_injector_inlet_pressure_pa),
        predicted_effective_cda_m2=injector_effective_cda_m2(context.injector_config),
        predicted_injector_cd=float(context.injector_config.cd),
        predicted_total_area_m2=predicted_total_area_m2,
        predicted_total_pressure_drop_pa=float(predicted_feed_delta_p_pa + predicted_injector_delta_p_pa),
        predicted_per_hole_velocity_m_s=float(predicted_per_hole_velocity_m_s),
        pressure_solution_source=pressure_solution_source,
        notes=notes,
    )


def predict_dataset(
    dataset: ColdFlowDataset,
    context: HydraulicModelContext,
    coldflow_config: Mapping[str, Any],
) -> list[HydraulicPrediction]:
    """Predict the hydraulic response for all points in a cold-flow dataset."""

    return [predict_point(point, context, coldflow_config) for point in dataset.points]
