"""Configuration defaults and loaders for the design workflow."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from project_data import load_project_defaults
from src.constants import DEFAULT_SENSITIVITY_METRICS, SUPPORTED_UNCERTAINTY_PARAMETERS
from src.io_utils import deep_merge, load_json


@dataclass(frozen=True)
class UncertaintySpec:
    mode: str
    value: float


@dataclass(frozen=True)
class CornerCaseDefinition:
    name: str
    adjustments: dict[str, Any]


DEFAULT_DESIGN_CONFIG: dict[str, Any] = deepcopy(load_project_defaults()["design_workflow"])


def _validate_uncertainty_section(section: Mapping[str, Any]) -> dict[str, UncertaintySpec]:
    validated: dict[str, UncertaintySpec] = {}
    for key, raw_spec in section.items():
        if key not in SUPPORTED_UNCERTAINTY_PARAMETERS:
            raise ValueError(f"Unsupported uncertainty parameter: {key}")
        mode = str(raw_spec["mode"]).lower()
        if mode not in {"percent", "absolute"}:
            raise ValueError(f"Uncertainty mode for {key} must be 'percent' or 'absolute'.")
        value = float(raw_spec["value"])
        if value < 0.0:
            raise ValueError(f"Uncertainty magnitude for {key} must be non-negative.")
        validated[key] = UncertaintySpec(mode=mode, value=value)
    return validated


def _derived_default_constraints(config: dict[str, Any]) -> dict[str, Any]:
    target_thrust_n = float(config["nominal"]["performance"]["target_thrust_n"])
    burn_time_s = float(config["nominal"]["blowdown"]["simulation"]["burn_time_s"])
    return {
        "pc_peak_bar": {"max": 60.0},
        "pc_avg_bar": {"min": 10.0},
        "thrust_avg_n": {"min": 0.75 * target_thrust_n},
        "thrust_peak_n": {"max": 1.50 * target_thrust_n},
        "of_avg": {"min": 2.0, "max": 12.0},
        "burn_time_actual_s": {"min": 0.8 * burn_time_s, "max": 1.2 * burn_time_s},
        "burn_time_target_met": {"allowed": [True]},
        "geometry_valid": {"allowed": [True]},
        "status": {"allowed": ["completed"]},
    }


def _normalize_geometry_policy(section: Mapping[str, Any]) -> dict[str, Any]:
    policy = deepcopy(dict(section))
    policy["baseline_port_count"] = int(policy.get("baseline_port_count", 1))
    if policy["baseline_port_count"] <= 0:
        raise ValueError("geometry_policy.baseline_port_count must be positive.")

    for key in (
        "single_port_baseline",
        "prechamber_enabled",
        "postchamber_enabled",
        "axial_showerhead_injector_baseline",
        "injector_discharges_to_prechamber",
        "lstar_report_only",
        "require_nominal_constraints_pass",
        "require_corner_constraints_pass",
        "use_nominal_case_for_cea_reference",
    ):
        if key in policy:
            policy[key] = bool(policy[key])

    for key in (
        "grain_to_chamber_radial_clearance_m",
        "injector_face_margin_factor",
        "max_injector_face_margin_factor",
        "injector_plate_thickness_m",
        "chamber_wall_thickness_guess_m",
        "min_radial_web_m",
        "min_burnout_web_m",
        "max_port_to_outer_radius_ratio",
        "max_grain_slenderness_ratio",
        "min_nozzle_area_ratio",
        "max_nozzle_area_ratio",
        "min_chamber_to_throat_diameter_ratio",
        "max_chamber_to_throat_diameter_ratio",
        "min_port_to_throat_diameter_ratio",
        "max_port_to_throat_diameter_ratio",
        "lstar_warning_min_m",
        "lstar_warning_max_m",
        "max_shell_outer_diameter_m",
        "max_hot_gas_diameter_m",
        "max_grain_length_m",
        "max_total_chamber_length_m",
        "max_nozzle_length_m",
        "max_exit_diameter_m",
        "min_initial_web_m",
        "min_final_web_m",
        "max_grain_slenderness",
        "max_web_slenderness",
        "min_lstar_m",
        "max_lstar_m",
        "k_pre",
        "k_post",
        "k_pre_min",
        "k_pre_max",
        "k_post_min",
        "k_post_max",
        "L_pre_min_m",
        "L_pre_max_m",
        "L_post_min_m",
        "L_post_max_m",
        "alpha_min_deg",
        "alpha_max_deg",
        "beta_min_deg",
        "beta_max_deg",
        "epsilon_min",
        "epsilon_max",
        "max_area_expansion_ratio",
        "radius_search_step_m",
    ):
        if key in policy and policy[key] is not None:
            policy[key] = float(policy[key])

    policy["prechamber_length_mode"] = str(policy.get("prechamber_length_mode", "hot_gas_diameter_fraction")).lower()
    policy["postchamber_length_mode"] = str(policy.get("postchamber_length_mode", "hot_gas_diameter_fraction")).lower()

    if policy["injector_face_margin_factor"] < 1.0:
        raise ValueError("geometry_policy.injector_face_margin_factor must be >= 1.0.")
    if policy["max_injector_face_margin_factor"] < policy["injector_face_margin_factor"]:
        raise ValueError("geometry_policy.max_injector_face_margin_factor must be >= injector_face_margin_factor.")
    return policy


def _normalize_performance_lookup(section: Mapping[str, Any]) -> dict[str, Any]:
    lookup = deepcopy(dict(section))
    lookup["enabled"] = bool(lookup.get("enabled", True))
    lookup["fallback_to_seed_on_failure"] = bool(lookup.get("fallback_to_seed_on_failure", True))
    lookup["of_padding"] = float(lookup.get("of_padding", 2.0))
    lookup["sample_count"] = int(lookup.get("sample_count", 9))
    if lookup["of_padding"] <= 0.0:
        raise ValueError("performance_lookup.of_padding must be positive.")
    if lookup["sample_count"] < 2:
        raise ValueError("performance_lookup.sample_count must be at least 2.")
    return lookup


def _normalize_internal_ballistics(section: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    settings = deepcopy(dict(section))
    settings["solver_mode"] = str(settings.get("solver_mode", "1d")).lower()
    if settings["solver_mode"] not in {"0d", "1d"}:
        raise ValueError("internal_ballistics.solver_mode must be '0d' or '1d'.")

    settings["axial_cell_count"] = int(settings.get("axial_cell_count", 31))
    settings["time_step_s"] = float(settings.get("time_step_s", config["nominal"]["blowdown"]["simulation"]["dt_s"]))
    settings["max_simulation_time_s"] = float(
        settings.get("max_simulation_time_s", config["nominal"]["blowdown"]["simulation"]["burn_time_s"])
    )
    settings["ambient_pressure_pa"] = float(
        settings.get("ambient_pressure_pa", config["nominal"]["blowdown"]["simulation"]["ambient_pressure_pa"])
    )
    settings["record_every_n_steps"] = int(settings.get("record_every_n_steps", 1))
    settings["station_sample_count"] = int(settings.get("station_sample_count", 3))
    settings["axial_head_end_bias_strength"] = float(settings.get("axial_head_end_bias_strength", 0.15))
    settings["axial_bias_decay_fraction"] = float(settings.get("axial_bias_decay_fraction", 0.35))
    settings["max_port_growth_fraction_per_step"] = float(settings.get("max_port_growth_fraction_per_step", 0.2))
    settings["max_pressure_iterations"] = int(settings.get("max_pressure_iterations", 80))
    settings["pressure_relaxation"] = float(settings.get("pressure_relaxation", 0.35))
    settings["pressure_relative_tolerance"] = float(settings.get("pressure_relative_tolerance", 1e-6))

    for key in (
        "auto_freeze_geometry_if_missing",
        "compare_to_0d",
    ):
        settings[key] = bool(settings.get(key, True))

    for key in (
        "prechamber_model_mode",
        "postchamber_model_mode",
        "performance_lookup_mode",
        "regression_model_mode",
        "geometry_input_source",
        "axial_correction_mode",
        "geometry_path",
    ):
        settings[key] = str(settings.get(key, "")).strip()

    if settings["axial_cell_count"] < 2:
        raise ValueError("internal_ballistics.axial_cell_count must be at least 2.")
    if settings["time_step_s"] <= 0.0:
        raise ValueError("internal_ballistics.time_step_s must be positive.")
    if settings["max_simulation_time_s"] <= 0.0:
        raise ValueError("internal_ballistics.max_simulation_time_s must be positive.")
    if settings["record_every_n_steps"] <= 0:
        raise ValueError("internal_ballistics.record_every_n_steps must be positive.")
    if settings["station_sample_count"] <= 0:
        raise ValueError("internal_ballistics.station_sample_count must be positive.")
    if settings["max_port_growth_fraction_per_step"] <= 0.0:
        raise ValueError("internal_ballistics.max_port_growth_fraction_per_step must be positive.")
    if settings["max_pressure_iterations"] <= 0:
        raise ValueError("internal_ballistics.max_pressure_iterations must be positive.")
    if not 0.0 < settings["pressure_relaxation"] <= 1.0:
        raise ValueError("internal_ballistics.pressure_relaxation must be in (0, 1].")
    if settings["pressure_relative_tolerance"] <= 0.0:
        raise ValueError("internal_ballistics.pressure_relative_tolerance must be positive.")
    if settings["axial_bias_decay_fraction"] <= 0.0:
        raise ValueError("internal_ballistics.axial_bias_decay_fraction must be positive.")
    if settings["geometry_input_source"] not in {"auto", "file", "freeze_nominal"}:
        raise ValueError("internal_ballistics.geometry_input_source must be 'auto', 'file', or 'freeze_nominal'.")
    if settings["performance_lookup_mode"] not in {"cea_table", "fixed_seed"}:
        raise ValueError("internal_ballistics.performance_lookup_mode must be 'cea_table' or 'fixed_seed'.")
    if settings["regression_model_mode"] != "power_law":
        raise ValueError("internal_ballistics.regression_model_mode currently supports only 'power_law'.")
    if settings["prechamber_model_mode"] != "lumped_volume":
        raise ValueError("internal_ballistics.prechamber_model_mode currently supports only 'lumped_volume'.")
    if settings["postchamber_model_mode"] != "lumped_volume":
        raise ValueError("internal_ballistics.postchamber_model_mode currently supports only 'lumped_volume'.")
    if settings["axial_correction_mode"] not in {"uniform", "showerhead_head_end_bias"}:
        raise ValueError(
            "internal_ballistics.axial_correction_mode must be 'uniform' or 'showerhead_head_end_bias'."
        )
    return settings


def _normalize_injector_design(section: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    settings = deepcopy(dict(section))
    settings["injector_type"] = str(settings.get("injector_type", "axial_showerhead")).lower()
    settings["solver_injector_source"] = str(settings.get("solver_injector_source", "equivalent_manual")).lower()
    settings["design_condition_source"] = str(settings.get("design_condition_source", "nominal_initial")).lower()
    settings["geometry_path"] = str(settings.get("geometry_path", "output/injector_design/injector_geometry.json")).strip()
    settings["engine_geometry_input_source"] = str(settings.get("engine_geometry_input_source", "auto")).lower()
    settings["engine_geometry_path"] = str(settings.get("engine_geometry_path", "output/geometry/geometry_definition.json")).strip()
    settings["preferred_hole_count_mode"] = str(settings.get("preferred_hole_count_mode", "list")).lower()
    settings["preferred_ring_spacing_mode"] = str(settings.get("preferred_ring_spacing_mode", "balanced")).lower()
    settings["discharge_edge_model"] = str(settings.get("discharge_edge_model", "sharp_edged")).lower()
    settings["backcalculation_mode"] = str(settings.get("backcalculation_mode", "edge_and_ld_heuristic")).lower()

    for key in ("auto_freeze_geometry_if_missing", "allow_center_hole"):
        settings[key] = bool(settings.get(key, True))

    allowed_hole_count_values = settings.get("allowed_hole_count_values", [config["nominal"]["blowdown"]["injector"]["hole_count"]])
    settings["allowed_hole_count_values"] = sorted(
        {
            int(value)
            for value in allowed_hole_count_values
        }
    )
    settings["preferred_hole_diameter_range_mm"] = [float(value) for value in settings.get("preferred_hole_diameter_range_mm", [1.0, 2.5])]

    for key in (
        "fixed_hole_diameter_mm",
        "minimum_hole_diameter_mm",
        "maximum_hole_diameter_mm",
        "minimum_ligament_mm",
        "minimum_edge_margin_mm",
        "preferred_plate_thickness_mm",
        "target_hole_ld_min",
        "target_hole_ld_max",
        "active_face_margin_factor",
        "plenum_depth_guess_mm",
        "face_to_grain_distance_guess_mm",
        "default_injector_cd",
        "maximum_open_area_ratio",
        "maximum_hole_velocity_m_s",
    ):
        settings[key] = float(settings.get(key))

    settings["maximum_ring_count"] = int(settings.get("maximum_ring_count", 6))
    settings["user_design_point"] = deepcopy(dict(settings.get("user_design_point", {})))
    for key in (
        "mdot_ox_kg_s",
        "injector_inlet_pressure_pa",
        "chamber_pressure_pa",
        "injector_delta_p_pa",
        "liquid_density_kg_m3",
        "tank_pressure_pa",
        "time_s",
    ):
        if key in settings["user_design_point"] and settings["user_design_point"][key] is not None:
            settings["user_design_point"][key] = float(settings["user_design_point"][key])

    if settings["injector_type"] != "axial_showerhead":
        raise ValueError("injector_design.injector_type currently supports only 'axial_showerhead'.")
    if settings["solver_injector_source"] not in {"equivalent_manual", "geometry_backcalculated"}:
        raise ValueError(
            "injector_design.solver_injector_source must be 'equivalent_manual' or 'geometry_backcalculated'."
        )
    if settings["design_condition_source"] not in {"nominal_initial", "nominal_average", "hot_case", "user_override"}:
        raise ValueError(
            "injector_design.design_condition_source must be 'nominal_initial', 'nominal_average', 'hot_case', or 'user_override'."
        )
    if settings["engine_geometry_input_source"] not in {"auto", "file", "freeze_nominal"}:
        raise ValueError(
            "injector_design.engine_geometry_input_source must be 'auto', 'file', or 'freeze_nominal'."
        )
    if settings["preferred_hole_count_mode"] != "list":
        raise ValueError("injector_design.preferred_hole_count_mode currently supports only 'list'.")
    if settings["preferred_ring_spacing_mode"] not in {"balanced", "minimum_pitch"}:
        raise ValueError(
            "injector_design.preferred_ring_spacing_mode must be 'balanced' or 'minimum_pitch'."
        )
    if settings["discharge_edge_model"] not in {"sharp_edged", "chamfered", "rounded"}:
        raise ValueError(
            "injector_design.discharge_edge_model must be 'sharp_edged', 'chamfered', or 'rounded'."
        )
    if settings["backcalculation_mode"] not in {"constant_cd", "edge_and_ld_heuristic"}:
        raise ValueError(
            "injector_design.backcalculation_mode must be 'constant_cd' or 'edge_and_ld_heuristic'."
        )
    if not settings["allowed_hole_count_values"] or min(settings["allowed_hole_count_values"]) <= 0:
        raise ValueError("injector_design.allowed_hole_count_values must contain positive integers.")
    if len(settings["preferred_hole_diameter_range_mm"]) != 2:
        raise ValueError("injector_design.preferred_hole_diameter_range_mm must contain exactly two values.")
    if settings["preferred_hole_diameter_range_mm"][0] <= 0.0 or settings["preferred_hole_diameter_range_mm"][1] <= 0.0:
        raise ValueError("injector_design.preferred_hole_diameter_range_mm entries must be positive.")
    if settings["preferred_hole_diameter_range_mm"][0] > settings["preferred_hole_diameter_range_mm"][1]:
        raise ValueError("injector_design.preferred_hole_diameter_range_mm must be ordered [min, max].")
    if settings["fixed_hole_diameter_mm"] <= 0.0:
        raise ValueError("injector_design.fixed_hole_diameter_mm must be positive.")
    if settings["minimum_hole_diameter_mm"] <= 0.0 or settings["maximum_hole_diameter_mm"] <= 0.0:
        raise ValueError("injector_design hole diameter limits must be positive.")
    if settings["minimum_hole_diameter_mm"] > settings["maximum_hole_diameter_mm"]:
        raise ValueError("injector_design.minimum_hole_diameter_mm must be <= maximum_hole_diameter_mm.")
    if settings["minimum_ligament_mm"] <= 0.0:
        raise ValueError("injector_design.minimum_ligament_mm must be positive.")
    if settings["minimum_edge_margin_mm"] <= 0.0:
        raise ValueError("injector_design.minimum_edge_margin_mm must be positive.")
    if settings["preferred_plate_thickness_mm"] <= 0.0:
        raise ValueError("injector_design.preferred_plate_thickness_mm must be positive.")
    if settings["target_hole_ld_min"] <= 0.0 or settings["target_hole_ld_max"] <= 0.0:
        raise ValueError("injector_design target hole L/D values must be positive.")
    if settings["target_hole_ld_min"] > settings["target_hole_ld_max"]:
        raise ValueError("injector_design.target_hole_ld_min must be <= target_hole_ld_max.")
    if settings["maximum_ring_count"] < 0:
        raise ValueError("injector_design.maximum_ring_count must be non-negative.")
    if not 0.0 < settings["active_face_margin_factor"] <= 1.0:
        raise ValueError("injector_design.active_face_margin_factor must be in (0, 1].")
    if settings["plenum_depth_guess_mm"] < 0.0:
        raise ValueError("injector_design.plenum_depth_guess_mm must be non-negative.")
    if settings["face_to_grain_distance_guess_mm"] < 0.0:
        raise ValueError("injector_design.face_to_grain_distance_guess_mm must be non-negative.")
    if not 0.0 < settings["default_injector_cd"] <= 1.0:
        raise ValueError("injector_design.default_injector_cd must be in (0, 1].")
    if settings["maximum_open_area_ratio"] <= 0.0:
        raise ValueError("injector_design.maximum_open_area_ratio must be positive.")
    if settings["maximum_hole_velocity_m_s"] <= 0.0:
        raise ValueError("injector_design.maximum_hole_velocity_m_s must be positive.")
    return settings


def _normalize_hydraulic_validation(section: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    settings = deepcopy(dict(section))
    settings["hydraulic_source"] = str(settings.get("hydraulic_source", "nominal_uncalibrated")).lower()
    settings["dataset_path"] = str(settings.get("dataset_path", "input/coldflow_dataset.csv")).strip()
    settings["dataset_format"] = str(settings.get("dataset_format", "auto")).lower()
    settings["dataset_name"] = str(settings.get("dataset_name", "hydraulic_dataset")).strip()
    settings["output_subdir"] = str(settings.get("output_subdir", "hydraulic_validation")).strip()
    settings["calibration_mode"] = str(settings.get("calibration_mode", "joint")).lower()
    settings["test_mode"] = str(settings.get("test_mode", "feed_plus_injector_rig")).lower()
    settings["injector_model_source"] = str(settings.get("injector_model_source", "solver_default")).lower()
    settings["injector_geometry_path"] = str(
        settings.get("injector_geometry_path", config["injector_design"]["geometry_path"])
    ).strip()
    settings["calibration_package_path"] = str(
        settings.get("calibration_package_path", "output/hydraulic_validation/calibration_package.json")
    ).strip()
    settings["comparison_package_path"] = str(
        settings.get("comparison_package_path", settings["calibration_package_path"])
    ).strip()

    for key in ("allow_missing_calibration_package", "force_disable_feed_model"):
        settings[key] = bool(settings.get(key, True if key == "allow_missing_calibration_package" else False))

    fluid = deepcopy(dict(settings.get("fluid", {})))
    fluid["name"] = str(fluid.get("name", "water")).strip()
    for key in ("temperature_k", "density_kg_m3"):
        if fluid.get(key) is not None:
            fluid[key] = float(fluid[key])
    fluid["is_surrogate"] = bool(fluid.get("is_surrogate", False))
    fluid["intended_application"] = str(fluid.get("intended_application", "general hydraulic validation")).strip()
    settings["fluid"] = fluid

    rig = deepcopy(dict(settings.get("rig", {})))
    rig["test_mode"] = str(rig.get("test_mode", settings["test_mode"])).lower()
    rig["pressure_tap_locations"] = dict(rig.get("pressure_tap_locations", {}))
    rig["line_geometry_known"] = bool(rig.get("line_geometry_known", False))
    rig["valve_filter_notes"] = [str(value) for value in rig.get("valve_filter_notes", [])]
    rig["injector_geometry_reference"] = str(
        rig.get("injector_geometry_reference", settings["injector_geometry_path"])
    ).strip()
    rig["calibration_assumptions"] = [str(value) for value in rig.get("calibration_assumptions", [])]
    rig["surrogate_fluid_used"] = bool(rig.get("surrogate_fluid_used", fluid["is_surrogate"]))
    rig["intended_application"] = str(
        rig.get("intended_application", fluid["intended_application"])
    ).strip()
    rig["notes"] = [str(value) for value in rig.get("notes", [])]
    rig["feed_model_override"] = dict(rig.get("feed_model_override", {}))
    for key in (
        "line_id_m",
        "line_length_m",
        "friction_factor",
        "minor_loss_k_total",
        "pressure_drop_multiplier",
        "manual_delta_p_pa",
    ):
        if rig["feed_model_override"].get(key) is not None:
            rig["feed_model_override"][key] = float(rig["feed_model_override"][key])
    settings["rig"] = rig

    ingest = deepcopy(dict(settings.get("ingest", {})))
    ingest["column_map"] = {str(key): str(value) for key, value in dict(ingest.get("column_map", {})).items()}
    ingest["unit_overrides"] = dict(ingest.get("unit_overrides", {}))
    ingest["field_aliases"] = {
        str(key): [str(item) for item in value]
        for key, value in dict(ingest.get("field_aliases", {})).items()
    }
    settings["ingest"] = ingest

    if settings["hydraulic_source"] not in {"nominal_uncalibrated", "coldflow_calibrated", "geometry_plus_coldflow"}:
        raise ValueError(
            "hydraulic_validation.hydraulic_source must be 'nominal_uncalibrated', 'coldflow_calibrated', or 'geometry_plus_coldflow'."
        )
    if settings["dataset_format"] not in {"auto", "csv", "json"}:
        raise ValueError("hydraulic_validation.dataset_format must be 'auto', 'csv', or 'json'.")
    if settings["calibration_mode"] not in {"injector_only", "feed_only", "joint"}:
        raise ValueError("hydraulic_validation.calibration_mode must be 'injector_only', 'feed_only', or 'joint'.")
    if settings["test_mode"] not in {"injector_only_bench", "feed_plus_injector_rig", "surrogate_fluid", "oxidizer_mode"}:
        raise ValueError(
            "hydraulic_validation.test_mode must be 'injector_only_bench', 'feed_plus_injector_rig', 'surrogate_fluid', or 'oxidizer_mode'."
        )
    if settings["injector_model_source"] not in {"solver_default", "equivalent_manual", "geometry_backcalculated"}:
        raise ValueError(
            "hydraulic_validation.injector_model_source must be 'solver_default', 'equivalent_manual', or 'geometry_backcalculated'."
        )
    if fluid.get("temperature_k") is not None and float(fluid["temperature_k"]) <= 0.0:
        raise ValueError("hydraulic_validation.fluid.temperature_k must be positive when provided.")
    if fluid.get("density_kg_m3") is not None and float(fluid["density_kg_m3"]) <= 0.0:
        raise ValueError("hydraulic_validation.fluid.density_kg_m3 must be positive when provided.")
    return settings


def _normalize_structural(section: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    settings = deepcopy(dict(section))
    settings["load_source"] = str(settings.get("load_source", "corner_case_envelope")).lower()
    settings["geometry_input_source"] = str(settings.get("geometry_input_source", "auto")).lower()
    settings["geometry_path"] = str(settings.get("geometry_path", "output/geometry/geometry_definition.json")).strip()
    settings["injector_geometry_input_source"] = str(settings.get("injector_geometry_input_source", "auto")).lower()
    settings["injector_geometry_path"] = str(
        settings.get("injector_geometry_path", config["injector_design"]["geometry_path"])
    ).strip()
    settings["allowable_basis"] = str(settings.get("allowable_basis", "yield_based")).lower()
    settings["closure_style"] = str(settings.get("closure_style", "bolted_flange")).lower()

    for key in (
        "auto_freeze_geometry_if_missing",
        "auto_synthesize_injector_if_missing",
        "allow_missing_injector_geometry",
        "include_nominal_initial_case",
        "include_nominal_peak_case",
        "include_corner_case_envelope",
        "include_internal_ballistics_peak_case",
    ):
        settings[key] = bool(settings.get(key, True))

    component_materials = deepcopy(
        dict(
            settings.get(
                "component_materials",
                {
                    "chamber_wall": "aluminum_6061_t6",
                    "forward_closure": "aluminum_6061_t6",
                    "aft_closure": "aluminum_6061_t6",
                    "injector_plate": "aluminum_6061_t6",
                    "nozzle_mount": "aluminum_6061_t6",
                    "fasteners": "steel_4140_qt",
                },
            )
        )
    )
    settings["component_materials"] = {str(key): str(value).strip() for key, value in component_materials.items()}

    custom_materials = deepcopy(dict(settings.get("custom_materials", {})))
    for material_key, raw_material in list(custom_materials.items()):
        material = dict(raw_material)
        material["material_name"] = str(material.get("material_name", material_key)).strip()
        for key in (
            "density_kg_m3",
            "yield_strength_pa",
            "ultimate_strength_pa",
            "allowable_stress_pa",
            "youngs_modulus_pa",
            "poisson_ratio",
            "max_service_temp_k",
        ):
            if material.get(key) is not None:
                material[key] = float(material[key])
        material["notes"] = [str(item) for item in material.get("notes", [])]
        custom_materials[material_key] = material
    settings["custom_materials"] = custom_materials

    policy = deepcopy(dict(settings.get("design_policy", {})))
    for key, default in (
        ("yield_safety_factor", 1.5),
        ("ultimate_safety_factor", 2.0),
        ("proof_factor", 1.25),
        ("burst_factor", 2.0),
        ("thin_wall_switch_ratio", 10.0),
        ("minimum_wall_thickness_m", 0.0025),
        ("minimum_flange_thickness_m", 0.0040),
        ("thickness_roundup_increment_m", 0.0005),
        ("default_bolt_preload_fraction", 0.65),
        ("mass_roundup_factor", 1.1),
        ("corrosion_or_manufacturing_allowance_m", 0.0005),
    ):
        policy[key] = float(policy.get(key, default))
    for key, default in (
        ("closure_model_type", "clamped_circular_plate"),
        ("injector_plate_model_type", "clamped_circular_plate"),
        ("nozzle_mount_model_type", "clamped_circular_plate"),
    ):
        policy[key] = str(policy.get(key, default)).lower()
    settings["design_policy"] = policy

    component_defaults = {
        "forward_closure": {"loaded_diameter_scale": 1.0},
        "aft_closure": {"loaded_diameter_scale": 1.0},
        "nozzle_mount": {"loaded_diameter_scale": 2.0, "separating_force_multiplier": 1.0},
        "injector_plate": {
            "unsupported_diameter_scale": 0.92,
            "open_area_warning_threshold": 0.25,
            "perforation_stress_multiplier_factor": 1.5,
        },
        "fasteners": {
            "fastener_count": 12,
            "nominal_diameter_m": 0.00635,
            "tensile_area_factor": 0.75,
            "joint_load_fraction": 1.0,
            "grip_length_m": 0.03,
        },
        "grain_support": {
            "retention_concept": "support_rings",
            "minimum_clearance_m": 0.001,
            "minimum_final_web_m": 0.001,
            "max_grain_slenderness_ratio": 15.0,
            "max_web_slenderness_ratio": 80.0,
        },
    }
    for section_name, defaults in component_defaults.items():
        section_payload = deepcopy(dict(settings.get(section_name, {})))
        for key, default in defaults.items():
            if key == "retention_concept":
                section_payload[key] = str(section_payload.get(key, default)).lower()
            elif isinstance(default, int):
                section_payload[key] = int(section_payload.get(key, default))
            else:
                section_payload[key] = float(section_payload.get(key, default))
        for key in ("loaded_diameter_m", "minimum_thickness_m", "unsupported_diameter_m", "selected_thickness_m"):
            if key in section_payload and section_payload.get(key) is not None:
                section_payload[key] = float(section_payload[key])
        settings[section_name] = section_payload

    user_override = deepcopy(dict(settings.get("user_override_load_case", {})))
    for key in (
        "chamber_pressure_pa",
        "injector_upstream_pressure_pa",
        "tank_pressure_pa",
        "ambient_pressure_pa",
        "injector_delta_p_pa",
        "feed_delta_p_pa",
        "axial_force_n",
        "nozzle_separating_force_n",
        "closure_separating_force_n",
    ):
        if user_override.get(key) is not None:
            user_override[key] = float(user_override[key])
    user_override["case_name"] = str(user_override.get("case_name", "user_override")).strip()
    user_override["source_stage"] = str(user_override.get("source_stage", "user_override")).strip()
    user_override["notes"] = [str(item) for item in user_override.get("notes", [])]
    settings["user_override_load_case"] = user_override

    if settings["load_source"] not in {"nominal_0d", "peak_1d", "corner_case_envelope", "user_override"}:
        raise ValueError(
            "structural.load_source must be 'nominal_0d', 'peak_1d', 'corner_case_envelope', or 'user_override'."
        )
    if settings["geometry_input_source"] not in {"auto", "file", "freeze_nominal"}:
        raise ValueError("structural.geometry_input_source must be 'auto', 'file', or 'freeze_nominal'.")
    if settings["injector_geometry_input_source"] not in {"auto", "file", "synthesize", "disabled"}:
        raise ValueError(
            "structural.injector_geometry_input_source must be 'auto', 'file', 'synthesize', or 'disabled'."
        )
    if settings["allowable_basis"] not in {"yield_based", "ultimate_based", "user_override"}:
        raise ValueError("structural.allowable_basis must be 'yield_based', 'ultimate_based', or 'user_override'.")
    if settings["closure_style"] not in {"bolted_flange", "tie_rod", "monolithic"}:
        raise ValueError("structural.closure_style must be 'bolted_flange', 'tie_rod', or 'monolithic'.")
    if policy["yield_safety_factor"] <= 1.0 or policy["ultimate_safety_factor"] <= 1.0:
        raise ValueError("structural safety factors must be greater than 1.0.")
    if policy["proof_factor"] <= 1.0 or policy["burst_factor"] <= 1.0:
        raise ValueError("structural proof and burst factors must be greater than 1.0.")
    if policy["thin_wall_switch_ratio"] <= 1.0:
        raise ValueError("structural.design_policy.thin_wall_switch_ratio must be greater than 1.0.")
    if policy["minimum_wall_thickness_m"] <= 0.0 or policy["minimum_flange_thickness_m"] <= 0.0:
        raise ValueError("structural minimum thickness values must be positive.")
    if policy["thickness_roundup_increment_m"] <= 0.0:
        raise ValueError("structural.design_policy.thickness_roundup_increment_m must be positive.")
    if not 0.0 < policy["default_bolt_preload_fraction"] < 1.0:
        raise ValueError("structural.design_policy.default_bolt_preload_fraction must be in (0, 1).")
    if policy["mass_roundup_factor"] < 1.0:
        raise ValueError("structural.design_policy.mass_roundup_factor must be >= 1.0.")
    if policy["corrosion_or_manufacturing_allowance_m"] < 0.0:
        raise ValueError("structural.design_policy.corrosion_or_manufacturing_allowance_m must be non-negative.")
    if policy["closure_model_type"] not in {"clamped_circular_plate", "simply_supported_circular_plate"}:
        raise ValueError(
            "structural.design_policy.closure_model_type must be 'clamped_circular_plate' or 'simply_supported_circular_plate'."
        )
    if policy["injector_plate_model_type"] not in {"clamped_circular_plate", "simply_supported_circular_plate"}:
        raise ValueError(
            "structural.design_policy.injector_plate_model_type must be 'clamped_circular_plate' or 'simply_supported_circular_plate'."
        )
    if policy["nozzle_mount_model_type"] not in {"clamped_circular_plate", "simply_supported_circular_plate"}:
        raise ValueError(
            "structural.design_policy.nozzle_mount_model_type must be 'clamped_circular_plate' or 'simply_supported_circular_plate'."
        )
    if settings["fasteners"]["fastener_count"] < 0:
        raise ValueError("structural.fasteners.fastener_count must be non-negative.")
    if settings["fasteners"]["nominal_diameter_m"] <= 0.0:
        raise ValueError("structural.fasteners.nominal_diameter_m must be positive.")
    if not 0.0 < settings["fasteners"]["tensile_area_factor"] <= 1.0:
        raise ValueError("structural.fasteners.tensile_area_factor must be in (0, 1].")
    if settings["fasteners"]["joint_load_fraction"] <= 0.0 or settings["fasteners"]["grip_length_m"] <= 0.0:
        raise ValueError("structural fastener load fraction and grip length must be positive.")
    if settings["injector_plate"]["open_area_warning_threshold"] <= 0.0:
        raise ValueError("structural.injector_plate.open_area_warning_threshold must be positive.")
    if settings["injector_plate"]["perforation_stress_multiplier_factor"] < 0.0:
        raise ValueError("structural.injector_plate.perforation_stress_multiplier_factor must be non-negative.")
    if settings["grain_support"]["minimum_clearance_m"] < 0.0 or settings["grain_support"]["minimum_final_web_m"] < 0.0:
        raise ValueError("structural grain-support minimum dimensions must be non-negative.")
    if settings["grain_support"]["max_grain_slenderness_ratio"] <= 0.0:
        raise ValueError("structural.grain_support.max_grain_slenderness_ratio must be positive.")
    if settings["grain_support"]["max_web_slenderness_ratio"] <= 0.0:
        raise ValueError("structural.grain_support.max_web_slenderness_ratio must be positive.")
    if settings["load_source"] == "user_override" and user_override.get("chamber_pressure_pa") is None:
        raise ValueError(
            "structural.user_override_load_case.chamber_pressure_pa is required for load_source='user_override'."
        )
    return settings


def _normalize_thermal(section: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    settings = deepcopy(dict(section))
    load_source = str(settings.get("load_source", settings.get("thermal_load_source", "corner_case_envelope"))).lower()
    if load_source == "peak_1d":
        load_source = "transient_1d"
    settings["load_source"] = load_source
    settings["geometry_input_source"] = str(settings.get("geometry_input_source", "auto")).lower()
    settings["geometry_path"] = str(settings.get("geometry_path", "output/geometry/geometry_definition.json")).strip()
    settings["injector_geometry_input_source"] = str(settings.get("injector_geometry_input_source", "auto")).lower()
    settings["injector_geometry_path"] = str(
        settings.get("injector_geometry_path", config["injector_design"]["geometry_path"])
    ).strip()

    for key in (
        "auto_freeze_geometry_if_missing",
        "auto_synthesize_injector_if_missing",
        "allow_missing_injector_geometry",
        "include_nominal_initial_case",
        "include_corner_case_envelope",
        "include_internal_ballistics_case",
    ):
        settings[key] = bool(settings.get(key, True))

    for key, default in (
        ("reference_chamber_temp_k", 3200.0),
        ("temperature_scale_exponent", 0.15),
    ):
        settings[key] = float(settings.get(key, default))

    region_gas_temp_scale = deepcopy(dict(settings.get("region_gas_temp_scale", {})))
    for key, default in (
        ("prechamber", 0.99),
        ("chamber", 1.0),
        ("postchamber", 0.98),
    ):
        region_gas_temp_scale[key] = float(region_gas_temp_scale.get(key, default))
    settings["region_gas_temp_scale"] = region_gas_temp_scale

    structural_materials = config["structural"]["component_materials"]
    component_materials = deepcopy(
        dict(
            settings.get(
                "component_materials",
                {
                    "chamber_wall": structural_materials["chamber_wall"],
                    "prechamber": structural_materials["chamber_wall"],
                    "postchamber": structural_materials["chamber_wall"],
                    "throat": structural_materials["chamber_wall"],
                    "diverging_nozzle": structural_materials["chamber_wall"],
                    "injector_face": structural_materials["injector_plate"],
                    "liner": "phenolic_liner",
                    "throat_insert": "graphite",
                },
            )
        )
    )
    settings["component_materials"] = {str(key): str(value).strip() for key, value in component_materials.items()}

    custom_materials = deepcopy(dict(settings.get("custom_materials", {})))
    for material_key, raw_material in list(custom_materials.items()):
        material = dict(raw_material)
        material["material_name"] = str(material.get("material_name", material_key)).strip()
        for key in (
            "density_kg_m3",
            "conductivity_w_mk",
            "heat_capacity_j_kgk",
            "diffusivity_m2_s",
            "emissivity",
            "max_service_temp_k",
            "melt_or_softening_temp_k",
        ):
            if material.get(key) is not None:
                material[key] = float(material[key])
        material["notes"] = [str(item) for item in material.get("notes", [])]
        custom_materials[material_key] = material
    settings["custom_materials"] = custom_materials

    policy = deepcopy(dict(settings.get("design_policy", {})))
    for key, default in (
        ("gas_side_htc_model", "bartz_like"),
        ("wall_model_type", "two_node_lumped"),
        ("outer_convection_model", "fixed_h"),
        ("temperature_limit_basis", "max_service_temp"),
    ):
        policy[key] = str(policy.get(key, default)).lower()
    for key, default in (
        ("throat_htc_multiplier", 1.35),
        ("injector_face_htc_multiplier", 0.95),
        ("outer_h_guess_w_m2k", 12.0),
        ("outer_ambient_temp_k", float(config["nominal"]["performance"]["fuel_temperature_k"])),
        ("surface_emissivity", 0.8),
        ("service_temp_margin_k", 40.0),
        ("thermal_roundup_increment_m", 0.0005),
        ("minimum_protection_thickness_m", 0.001),
    ):
        policy[key] = float(policy.get(key, default))
    for key, default in (
        ("use_lumped_wall_model", True),
        ("radiation_enabled", True),
        ("sacrificial_liner_allowed", True),
        ("sacrificial_throat_insert_allowed", True),
    ):
        policy[key] = bool(policy.get(key, default))
    policy["inner_wall_node_count"] = int(policy.get("inner_wall_node_count", 2))
    settings["design_policy"] = policy

    nozzle_geometry = deepcopy(dict(settings.get("nozzle_geometry", {})))
    for key, default in (
        ("converging_half_angle_deg", 45.0),
        ("diverging_half_angle_deg", 15.0),
        ("throat_blend_radius_factor", 1.5),
    ):
        nozzle_geometry[key] = float(nozzle_geometry.get(key, default))
    settings["nozzle_geometry"] = nozzle_geometry
    for key, default in (
        ("maximum_shell_inner_wall_temp_k", 900.0),
        ("minimum_remaining_liner_thickness_m", 0.0),
        ("rho_liner", 1350.0),
        ("H_ablation_effective", 2.5e6),
        ("T_pyrolysis_k", 650.0),
    ):
        settings[key] = float(settings.get(key, default))
    settings["use_ablative_liner_model"] = bool(settings.get("use_ablative_liner_model", False))

    for section_name in ("chamber", "throat", "diverging_nozzle", "injector_face"):
        section_payload = deepcopy(dict(settings.get(section_name, {})))
        if section_payload.get("selected_wall_thickness_m") is not None:
            section_payload["selected_wall_thickness_m"] = float(section_payload["selected_wall_thickness_m"])
        if section_payload.get("selected_thickness_m") is not None:
            section_payload["selected_thickness_m"] = float(section_payload["selected_thickness_m"])
        if section_name == "throat":
            section_payload["axial_length_scale"] = float(section_payload.get("axial_length_scale", 1.0))
        settings[section_name] = section_payload

    for section_name in ("liner", "throat_insert"):
        section_payload = deepcopy(dict(settings.get(section_name, {})))
        section_payload["enabled"] = bool(section_payload.get("enabled", False))
        if section_payload.get("selected_thickness_m") is not None:
            section_payload["selected_thickness_m"] = float(section_payload["selected_thickness_m"])
        settings[section_name] = section_payload

    user_override = deepcopy(dict(settings.get("user_override_load_case", {})))
    for key in (
        "burn_time_s",
        "time_step_s",
        "chamber_pressure_pa",
        "mdot_total_kg_s",
        "mdot_ox_kg_s",
        "mdot_f_kg_s",
        "of_ratio",
        "cstar_mps",
        "cf_actual",
        "chamber_temp_k",
        "gamma",
        "ambient_pressure_pa",
    ):
        if user_override.get(key) is not None:
            user_override[key] = float(user_override[key])
    user_override["case_name"] = str(user_override.get("case_name", "user_override")).strip()
    user_override["source_stage"] = str(user_override.get("source_stage", "user_override")).strip()
    user_override["notes"] = [str(item) for item in user_override.get("notes", [])]
    settings["user_override_load_case"] = user_override

    if settings["load_source"] not in {"nominal_0d", "transient_1d", "corner_case_envelope", "user_override"}:
        raise ValueError(
            "thermal.load_source must be 'nominal_0d', 'transient_1d', 'corner_case_envelope', or 'user_override'."
        )
    if settings["geometry_input_source"] not in {"auto", "file", "freeze_nominal"}:
        raise ValueError("thermal.geometry_input_source must be 'auto', 'file', or 'freeze_nominal'.")
    if settings["injector_geometry_input_source"] not in {"auto", "file", "synthesize", "disabled"}:
        raise ValueError(
            "thermal.injector_geometry_input_source must be 'auto', 'file', 'synthesize', or 'disabled'."
        )
    if policy["gas_side_htc_model"] != "bartz_like":
        raise ValueError("thermal.design_policy.gas_side_htc_model currently supports only 'bartz_like'.")
    if policy["wall_model_type"] != "two_node_lumped":
        raise ValueError("thermal.design_policy.wall_model_type currently supports only 'two_node_lumped'.")
    if policy["outer_convection_model"] != "fixed_h":
        raise ValueError("thermal.design_policy.outer_convection_model currently supports only 'fixed_h'.")
    if policy["temperature_limit_basis"] not in {"max_service_temp", "softening_temp"}:
        raise ValueError("thermal.design_policy.temperature_limit_basis must be 'max_service_temp' or 'softening_temp'.")
    if policy["throat_htc_multiplier"] <= 0.0 or policy["injector_face_htc_multiplier"] <= 0.0:
        raise ValueError("thermal HTC multipliers must be positive.")
    if policy["outer_h_guess_w_m2k"] <= 0.0:
        raise ValueError("thermal.design_policy.outer_h_guess_w_m2k must be positive.")
    if policy["outer_ambient_temp_k"] <= 0.0:
        raise ValueError("thermal.design_policy.outer_ambient_temp_k must be positive.")
    if not 0.0 < policy["surface_emissivity"] <= 1.0:
        raise ValueError("thermal.design_policy.surface_emissivity must be in (0, 1].")
    if policy["service_temp_margin_k"] < 0.0:
        raise ValueError("thermal.design_policy.service_temp_margin_k must be non-negative.")
    if policy["thermal_roundup_increment_m"] <= 0.0 or policy["minimum_protection_thickness_m"] <= 0.0:
        raise ValueError("thermal protection thickness increments must be positive.")
    if settings["reference_chamber_temp_k"] <= 0.0:
        raise ValueError("thermal.reference_chamber_temp_k must be positive.")
    if settings["temperature_scale_exponent"] < 0.0:
        raise ValueError("thermal.temperature_scale_exponent must be non-negative.")
    if settings["load_source"] == "user_override" and user_override.get("chamber_pressure_pa") is None:
        raise ValueError("thermal.user_override_load_case.chamber_pressure_pa is required for load_source='user_override'.")
    if settings["load_source"] == "user_override" and user_override.get("chamber_temp_k") is None:
        raise ValueError("thermal.user_override_load_case.chamber_temp_k is required for load_source='user_override'.")
    return settings


def _normalize_nozzle_offdesign(section: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    settings = deepcopy(dict(section))
    source_mode = str(settings.get("source_mode", settings.get("nozzle_offdesign_source", "nominal_0d"))).lower()
    if source_mode == "peak_1d":
        source_mode = "transient_1d"
    settings["source_mode"] = source_mode
    settings["geometry_input_source"] = str(settings.get("geometry_input_source", "auto")).lower()
    settings["geometry_path"] = str(settings.get("geometry_path", "output/geometry/geometry_definition.json")).strip()
    settings["injector_geometry_input_source"] = str(settings.get("injector_geometry_input_source", "auto")).lower()
    settings["injector_geometry_path"] = str(
        settings.get("injector_geometry_path", config["injector_design"]["geometry_path"])
    ).strip()
    settings["performance_model"] = str(settings.get("performance_model", "reuse_solver_nozzle_model")).lower()
    settings["exit_pressure_mode"] = str(settings.get("exit_pressure_mode", "history_ratio")).lower()
    settings["separation_risk_model"] = str(settings.get("separation_risk_model", "pressure_ratio_heuristic")).lower()
    settings["steady_point_mode"] = str(settings.get("steady_point_mode", "peak_pc")).lower()

    for key in (
        "auto_freeze_geometry_if_missing",
        "auto_synthesize_injector_if_missing",
        "allow_missing_injector_geometry",
        "include_corner_case_envelope",
        "include_internal_ballistics_case",
        "use_transient_time_history",
    ):
        settings[key] = bool(settings.get(key, True))

    for key, default in (
        ("transient_sample_count", 25),
        ("reference_chamber_temp_k", 3200.0),
        ("temperature_scale_exponent", 0.15),
    ):
        settings[key] = float(settings.get(key, default)) if key != "transient_sample_count" else int(settings.get(key, default))

    if settings.get("fallback_exit_pressure_ratio") is not None:
        settings["fallback_exit_pressure_ratio"] = float(settings["fallback_exit_pressure_ratio"])
    if settings.get("selected_time_indices") is not None:
        settings["selected_time_indices"] = [int(value) for value in settings.get("selected_time_indices", [])]

    ambient_cases = []
    for raw_case in list(settings.get("ambient_cases", [])):
        case = dict(raw_case)
        case["case_name"] = str(case.get("case_name", "")).strip() or "ambient_case"
        case["environment_type"] = str(case.get("environment_type", "user_override")).strip().lower()
        if case.get("ambient_pressure_pa") is not None:
            case["ambient_pressure_pa"] = float(case["ambient_pressure_pa"])
        if case.get("ambient_temperature_k") is not None:
            case["ambient_temperature_k"] = float(case["ambient_temperature_k"])
        if case.get("altitude_m") is not None:
            case["altitude_m"] = float(case["altitude_m"])
        case["notes"] = [str(item) for item in case.get("notes", [])]
        ambient_cases.append(case)
    settings["ambient_cases"] = ambient_cases

    ambient_sweep = deepcopy(dict(settings.get("ambient_sweep", {})))
    ambient_sweep["enabled"] = bool(ambient_sweep.get("enabled", False))
    for key, default in (
        ("minimum_altitude_m", 0.0),
        ("maximum_altitude_m", 30000.0),
    ):
        ambient_sweep[key] = float(ambient_sweep.get(key, default))
    ambient_sweep["case_count"] = int(ambient_sweep.get("case_count", 6))
    ambient_sweep["include_vacuum_case"] = bool(ambient_sweep.get("include_vacuum_case", True))
    settings["ambient_sweep"] = ambient_sweep

    ascent_profile = deepcopy(dict(settings.get("ascent_profile", {})))
    ascent_profile["enabled"] = bool(ascent_profile.get("enabled", False))
    ascent_profile["altitude_points_m"] = [float(value) for value in ascent_profile.get("altitude_points_m", [])]
    settings["ascent_profile"] = ascent_profile

    expansion_thresholds = deepcopy(dict(settings.get("expansion_thresholds", {})))
    for key, default in (
        ("strongly_overexpanded_ratio", 0.40),
        ("moderately_overexpanded_ratio", 0.80),
        ("near_matched_upper_ratio", 1.20),
        ("moderately_underexpanded_ratio", 2.00),
    ):
        expansion_thresholds[key] = float(expansion_thresholds.get(key, default))
    settings["expansion_thresholds"] = expansion_thresholds

    separation_thresholds = deepcopy(dict(settings.get("separation_thresholds", {})))
    for key, default in (
        ("high_risk_ratio", 0.35),
        ("moderate_risk_ratio", 0.60),
        ("underexpanded_notice_ratio", 2.50),
        ("startup_window_fraction", 0.10),
        ("shutdown_window_fraction", 0.15),
    ):
        separation_thresholds[key] = float(separation_thresholds.get(key, default))
    settings["separation_thresholds"] = separation_thresholds

    penalties = deepcopy(dict(settings.get("penalties", {})))
    penalties["apply_separation_cf_penalty"] = bool(penalties.get("apply_separation_cf_penalty", False))
    for key, default in (
        ("moderate_risk_cf_multiplier", 0.97),
        ("high_risk_cf_multiplier", 0.90),
    ):
        penalties[key] = float(penalties.get(key, default))
    settings["penalties"] = penalties

    recommendations = deepcopy(dict(settings.get("recommendations", {})))
    recommendations["recommend_separate_ground_test_nozzle"] = bool(
        recommendations.get("recommend_separate_ground_test_nozzle", True)
    )
    for key, default in (
        ("ground_test_penalty_fraction_limit", 0.18),
        ("structural_margin_warning_threshold", 0.15),
        ("thermal_margin_warning_k", 50.0),
    ):
        recommendations[key] = float(recommendations.get(key, default))
    recommendations["comparison_area_ratios"] = [float(value) for value in recommendations.get("comparison_area_ratios", [])]
    settings["recommendations"] = recommendations

    user_override_source = deepcopy(dict(settings.get("user_override_source", {})))
    for key in (
        "burn_time_s",
        "time_step_s",
        "chamber_pressure_pa",
        "mdot_total_kg_s",
        "cf_vac",
        "cstar_mps",
        "gamma_e",
        "molecular_weight_exit",
        "exit_pressure_bar",
        "reference_chamber_temp_k",
    ):
        if user_override_source.get(key) is not None:
            user_override_source[key] = float(user_override_source[key])
    settings["user_override_source"] = user_override_source

    if settings["source_mode"] not in {"nominal_0d", "transient_1d", "corner_case_envelope", "user_override"}:
        raise ValueError(
            "nozzle_offdesign.source_mode must be 'nominal_0d', 'transient_1d', 'corner_case_envelope', or 'user_override'."
        )
    if settings["geometry_input_source"] not in {"auto", "file", "freeze_nominal"}:
        raise ValueError("nozzle_offdesign.geometry_input_source must be 'auto', 'file', or 'freeze_nominal'.")
    if settings["injector_geometry_input_source"] not in {"auto", "file", "synthesize", "disabled"}:
        raise ValueError(
            "nozzle_offdesign.injector_geometry_input_source must be 'auto', 'file', 'synthesize', or 'disabled'."
        )
    if settings["performance_model"] != "reuse_solver_nozzle_model":
        raise ValueError("nozzle_offdesign.performance_model currently supports only 'reuse_solver_nozzle_model'.")
    if settings["exit_pressure_mode"] != "history_ratio":
        raise ValueError("nozzle_offdesign.exit_pressure_mode currently supports only 'history_ratio'.")
    if settings["separation_risk_model"] != "pressure_ratio_heuristic":
        raise ValueError("nozzle_offdesign.separation_risk_model currently supports only 'pressure_ratio_heuristic'.")
    if settings["steady_point_mode"] not in {"initial", "peak_pc", "final"}:
        raise ValueError("nozzle_offdesign.steady_point_mode must be 'initial', 'peak_pc', or 'final'.")
    if settings["transient_sample_count"] <= 0:
        raise ValueError("nozzle_offdesign.transient_sample_count must be positive.")
    if settings["reference_chamber_temp_k"] <= 0.0:
        raise ValueError("nozzle_offdesign.reference_chamber_temp_k must be positive.")
    if settings["temperature_scale_exponent"] < 0.0:
        raise ValueError("nozzle_offdesign.temperature_scale_exponent must be non-negative.")
    if settings.get("fallback_exit_pressure_ratio") is not None and float(settings["fallback_exit_pressure_ratio"]) < 0.0:
        raise ValueError("nozzle_offdesign.fallback_exit_pressure_ratio must be non-negative when provided.")
    if expansion_thresholds["strongly_overexpanded_ratio"] <= 0.0:
        raise ValueError("nozzle_offdesign.expansion_thresholds.strongly_overexpanded_ratio must be positive.")
    if expansion_thresholds["moderately_overexpanded_ratio"] < expansion_thresholds["strongly_overexpanded_ratio"]:
        raise ValueError("nozzle_offdesign overexpansion thresholds must be ordered from strict to relaxed.")
    if expansion_thresholds["near_matched_upper_ratio"] < expansion_thresholds["moderately_overexpanded_ratio"]:
        raise ValueError("nozzle_offdesign.near_matched_upper_ratio must be >= moderately_overexpanded_ratio.")
    if expansion_thresholds["moderately_underexpanded_ratio"] < expansion_thresholds["near_matched_upper_ratio"]:
        raise ValueError("nozzle_offdesign.moderately_underexpanded_ratio must be >= near_matched_upper_ratio.")
    if separation_thresholds["high_risk_ratio"] <= 0.0 or separation_thresholds["moderate_risk_ratio"] <= 0.0:
        raise ValueError("nozzle_offdesign separation-risk ratios must be positive.")
    if separation_thresholds["moderate_risk_ratio"] < separation_thresholds["high_risk_ratio"]:
        raise ValueError("nozzle_offdesign moderate separation-risk ratio must be >= high-risk ratio.")
    if not 0.0 < separation_thresholds["startup_window_fraction"] <= 1.0:
        raise ValueError("nozzle_offdesign.startup_window_fraction must be in (0, 1].")
    if not 0.0 < separation_thresholds["shutdown_window_fraction"] <= 1.0:
        raise ValueError("nozzle_offdesign.shutdown_window_fraction must be in (0, 1].")
    if penalties["moderate_risk_cf_multiplier"] <= 0.0 or penalties["high_risk_cf_multiplier"] <= 0.0:
        raise ValueError("nozzle_offdesign penalty multipliers must be positive.")
    if penalties["high_risk_cf_multiplier"] > penalties["moderate_risk_cf_multiplier"]:
        raise ValueError("nozzle_offdesign high-risk penalty must be <= the moderate-risk penalty.")
    if recommendations["ground_test_penalty_fraction_limit"] < 0.0:
        raise ValueError("nozzle_offdesign.recommendations.ground_test_penalty_fraction_limit must be non-negative.")
    if recommendations["structural_margin_warning_threshold"] < 0.0:
        raise ValueError("nozzle_offdesign.recommendations.structural_margin_warning_threshold must be non-negative.")
    if recommendations["thermal_margin_warning_k"] < 0.0:
        raise ValueError("nozzle_offdesign.recommendations.thermal_margin_warning_k must be non-negative.")
    if ambient_sweep["enabled"] and ambient_sweep["case_count"] <= 0:
        raise ValueError("nozzle_offdesign.ambient_sweep.case_count must be positive when sweep is enabled.")
    if settings["source_mode"] == "user_override" and user_override_source.get("chamber_pressure_pa") is None:
        raise ValueError("nozzle_offdesign.user_override_source.chamber_pressure_pa is required for source_mode='user_override'.")
    return settings


def _normalize_cfd(section: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    settings = deepcopy(dict(section))
    default_targets = [
        "injector_plenum_plate_flow",
        "headend_prechamber_distribution",
        "nozzle_local_offdesign",
        "reacting_internal_region_refinement",
    ]
    supported_targets = set(default_targets)
    settings["cfd_case_source"] = str(settings.get("cfd_case_source", settings.get("case_source", "nominal_workflow"))).lower()
    settings["cfd_corrections_source"] = str(
        settings.get("cfd_corrections_source", settings.get("corrections_source", "combined"))
    ).lower()
    settings["enabled_targets"] = [str(item) for item in settings.get("enabled_targets", default_targets)]
    settings["target_priority_order"] = [str(item) for item in settings.get("target_priority_order", default_targets)]
    settings["geometry_input_source"] = str(settings.get("geometry_input_source", "auto")).lower()
    settings["geometry_path"] = str(settings.get("geometry_path", "output/geometry/geometry_definition.json")).strip()
    settings["injector_geometry_input_source"] = str(settings.get("injector_geometry_input_source", "auto")).lower()
    settings["injector_geometry_path"] = str(
        settings.get("injector_geometry_path", config["injector_design"]["geometry_path"])
    ).strip()
    settings["preferred_export_formats"] = [str(item).lower() for item in settings.get("preferred_export_formats", ["json", "csv"])]
    settings["turbulence_model"] = str(settings.get("turbulence_model", "sst_k_omega_placeholder")).strip()
    settings["wall_treatment"] = str(settings.get("wall_treatment", "automatic_placeholder")).strip()
    settings["result_ingest_path"] = str(settings.get("result_ingest_path", "")).strip()
    settings["result_ingest_format"] = str(settings.get("result_ingest_format", "auto")).lower()

    for key in (
        "auto_generate_campaign_plan",
        "auto_freeze_geometry_if_missing",
        "auto_synthesize_injector_if_missing",
        "allow_missing_injector_geometry",
        "include_internal_ballistics_case",
        "include_corner_case_envelope",
        "include_startup_shutdown_points",
        "include_nominal_average_point",
        "include_hot_cold_corner_points",
        "generate_correction_templates",
        "require_coldflow_before_stage1",
        "require_internal_ballistics_before_stage2",
        "require_nozzle_offdesign_before_stage3",
    ):
        settings[key] = bool(settings.get(key, True))

    recommended_solver_classes = deepcopy(dict(settings.get("recommended_solver_classes", {})))
    recommended_solver_classes.setdefault("injector_plenum", "pressure_based_nonreacting")
    recommended_solver_classes.setdefault("headend_prechamber", "pressure_based_nonreacting")
    recommended_solver_classes.setdefault("nozzle_local", "compressible_rans")
    recommended_solver_classes.setdefault("reacting_internal_region", "reacting_rans_placeholder")
    settings["recommended_solver_classes"] = {str(key): str(value) for key, value in recommended_solver_classes.items()}

    geometry_simplifications = deepcopy(dict(settings.get("geometry_simplifications", {})))
    for key, default in (
        ("suppress_small_fillet_details", True),
        ("collapse_small_hole_chamfers", True),
        ("allow_periodic_sector_model", False),
        ("truncate_far_downstream_volume", True),
    ):
        geometry_simplifications[key] = bool(geometry_simplifications.get(key, default))
    settings["geometry_simplifications"] = geometry_simplifications

    if settings["cfd_case_source"] not in {"nominal_workflow", "corner_case_envelope", "user_override"}:
        raise ValueError("cfd.cfd_case_source must be 'nominal_workflow', 'corner_case_envelope', or 'user_override'.")
    if settings["cfd_corrections_source"] not in {"none", "injector_only", "headend_only", "nozzle_only", "combined", "all"}:
        raise ValueError(
            "cfd.cfd_corrections_source must be 'none', 'injector_only', 'headend_only', 'nozzle_only', 'combined', or 'all'."
        )
    if settings["geometry_input_source"] not in {"auto", "file", "freeze_nominal"}:
        raise ValueError("cfd.geometry_input_source must be 'auto', 'file', or 'freeze_nominal'.")
    if settings["injector_geometry_input_source"] not in {"auto", "file", "synthesize", "disabled"}:
        raise ValueError("cfd.injector_geometry_input_source must be 'auto', 'file', 'synthesize', or 'disabled'.")
    if settings["result_ingest_format"] not in {"auto", "json", "csv"}:
        raise ValueError("cfd.result_ingest_format must be 'auto', 'json', or 'csv'.")
    if not settings["enabled_targets"]:
        raise ValueError("cfd.enabled_targets must contain at least one target name.")
    if any(target not in supported_targets for target in settings["enabled_targets"]):
        raise ValueError(f"cfd.enabled_targets contains unsupported targets: {settings['enabled_targets']}")
    if any(target not in supported_targets for target in settings["target_priority_order"]):
        raise ValueError(f"cfd.target_priority_order contains unsupported targets: {settings['target_priority_order']}")
    if set(settings["enabled_targets"]) - set(settings["target_priority_order"]):
        raise ValueError("cfd.target_priority_order must include every enabled CFD target.")
    if any(fmt not in {"json", "csv"} for fmt in settings["preferred_export_formats"]):
        raise ValueError("cfd.preferred_export_formats currently supports only 'json' and 'csv'.")
    return settings


def _normalize_testing(section: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    settings = deepcopy(dict(section))
    default_stages = [
        "material_coupon",
        "hydraulic_validation",
        "subscale_hotfire",
        "fullscale_short_duration",
        "fullscale_nominal_duration",
    ]
    supported_stages = set(default_stages)
    settings["test_campaign_source"] = str(settings.get("test_campaign_source", settings.get("campaign_source", "nominal_workflow"))).lower()
    settings["model_vs_test_source"] = str(settings.get("model_vs_test_source", "0d")).lower()
    settings["hotfire_corrections_source"] = str(settings.get("hotfire_corrections_source", "staged_combined")).lower()
    settings["readiness_source"] = str(settings.get("readiness_source", "configured_progression_gates")).lower()
    settings["dataset_path"] = str(settings.get("dataset_path", "")).strip()
    settings["dataset_format"] = str(settings.get("dataset_format", "auto")).lower()
    settings["enabled_stages"] = [str(item) for item in settings.get("enabled_stages", default_stages)]
    settings["stage_order"] = [str(item) for item in settings.get("stage_order", default_stages)]
    settings["geometry_reference_label"] = str(settings.get("geometry_reference_label", "frozen_geometry")).strip()
    for key in (
        "include_internal_ballistics_case",
        "include_corner_case_envelope",
        "include_cfd_context",
        "require_coldflow_before_hotfire",
        "require_internal_ballistics_before_subscale",
        "require_nozzle_offdesign_before_fullscale",
        "require_cfd_before_fullscale",
    ):
        settings[key] = bool(settings.get(key, True))

    article_scaling = deepcopy(dict(settings.get("article_scaling", {})))
    article_scaling["subscale_linear_scale"] = float(article_scaling.get("subscale_linear_scale", 0.5))
    article_scaling["nominal_burn_time_s"] = float(
        article_scaling.get("nominal_burn_time_s", config["nominal"]["blowdown"]["simulation"]["burn_time_s"])
    )
    settings["article_scaling"] = article_scaling

    instrumentation_defaults = deepcopy(dict(settings.get("instrumentation_defaults", {})))
    instrumentation_defaults["coldflow_sampling_rate_hz"] = float(instrumentation_defaults.get("coldflow_sampling_rate_hz", 100.0))
    instrumentation_defaults["hotfire_sampling_rate_hz"] = float(instrumentation_defaults.get("hotfire_sampling_rate_hz", 1000.0))
    settings["instrumentation_defaults"] = instrumentation_defaults

    ingest = deepcopy(dict(settings.get("ingest", {})))
    ingest["channel_map"] = {str(key): str(value) for key, value in dict(ingest.get("channel_map", {})).items()}
    ingest["dataset_metadata_defaults"] = dict(ingest.get("dataset_metadata_defaults", {}))
    settings["ingest"] = ingest

    data_cleaning = deepcopy(dict(settings.get("data_cleaning", {})))
    data_cleaning["padding_pre_s"] = float(data_cleaning.get("padding_pre_s", 0.05))
    data_cleaning["padding_post_s"] = float(data_cleaning.get("padding_post_s", 0.05))
    settings["data_cleaning"] = data_cleaning

    thresholds = deepcopy(dict(settings.get("progression_thresholds", {})))
    thresholds["allowed_pressure_trace_error_percent"] = float(thresholds.get("allowed_pressure_trace_error_percent", 15.0))
    thresholds["allowed_thrust_trace_error_percent"] = float(thresholds.get("allowed_thrust_trace_error_percent", 15.0))
    thresholds["allowed_burn_time_error_percent"] = float(thresholds.get("allowed_burn_time_error_percent", 15.0))
    thresholds["repeatability_cv_limit_percent"] = float(thresholds.get("repeatability_cv_limit_percent", 5.0))
    thresholds["thermal_warning_threshold_k"] = float(thresholds.get("thermal_warning_threshold_k", 50.0))
    thresholds["minimum_repeat_runs"] = int(thresholds.get("minimum_repeat_runs", 2))
    settings["progression_thresholds"] = thresholds

    if settings["test_campaign_source"] not in {"nominal_workflow", "corner_case_envelope", "user_override"}:
        raise ValueError("testing.test_campaign_source must be 'nominal_workflow', 'corner_case_envelope', or 'user_override'.")
    if settings["model_vs_test_source"] not in {"0d", "1d", "transient_1d"}:
        raise ValueError("testing.model_vs_test_source must be '0d', '1d', or 'transient_1d'.")
    if settings["hotfire_corrections_source"] not in {"none", "subscale_only", "fullscale_only", "staged_combined"}:
        raise ValueError("testing.hotfire_corrections_source must be 'none', 'subscale_only', 'fullscale_only', or 'staged_combined'.")
    if settings["readiness_source"] != "configured_progression_gates":
        raise ValueError("testing.readiness_source currently supports only 'configured_progression_gates'.")
    if settings["dataset_format"] not in {"auto", "json", "csv"}:
        raise ValueError("testing.dataset_format must be 'auto', 'json', or 'csv'.")
    if not settings["enabled_stages"]:
        raise ValueError("testing.enabled_stages must contain at least one stage.")
    if any(stage not in supported_stages for stage in settings["enabled_stages"]):
        raise ValueError(f"testing.enabled_stages contains unsupported stages: {settings['enabled_stages']}")
    if any(stage not in supported_stages for stage in settings["stage_order"]):
        raise ValueError(f"testing.stage_order contains unsupported stages: {settings['stage_order']}")
    if set(settings["enabled_stages"]) - set(settings["stage_order"]):
        raise ValueError("testing.stage_order must include every enabled testing stage.")
    if settings["article_scaling"]["subscale_linear_scale"] <= 0.0 or settings["article_scaling"]["subscale_linear_scale"] > 1.0:
        raise ValueError("testing.article_scaling.subscale_linear_scale must be in (0, 1].")
    if settings["article_scaling"]["nominal_burn_time_s"] <= 0.0:
        raise ValueError("testing.article_scaling.nominal_burn_time_s must be positive.")
    if settings["instrumentation_defaults"]["coldflow_sampling_rate_hz"] <= 0.0:
        raise ValueError("testing.instrumentation_defaults.coldflow_sampling_rate_hz must be positive.")
    if settings["instrumentation_defaults"]["hotfire_sampling_rate_hz"] <= 0.0:
        raise ValueError("testing.instrumentation_defaults.hotfire_sampling_rate_hz must be positive.")
    if settings["progression_thresholds"]["allowed_pressure_trace_error_percent"] < 0.0:
        raise ValueError("testing.allowed_pressure_trace_error_percent must be non-negative.")
    if settings["progression_thresholds"]["allowed_thrust_trace_error_percent"] < 0.0:
        raise ValueError("testing.allowed_thrust_trace_error_percent must be non-negative.")
    if settings["progression_thresholds"]["allowed_burn_time_error_percent"] < 0.0:
        raise ValueError("testing.allowed_burn_time_error_percent must be non-negative.")
    if settings["progression_thresholds"]["minimum_repeat_runs"] <= 0:
        raise ValueError("testing.minimum_repeat_runs must be positive.")
    return settings


def normalize_hydraulic_validation_config(section: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    return _normalize_hydraulic_validation(section, config)


def normalize_structural_config(section: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    return _normalize_structural(section, config)


def normalize_thermal_config(section: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    return _normalize_thermal(section, config)


def normalize_nozzle_offdesign_config(section: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    return _normalize_nozzle_offdesign(section, config)


def normalize_cfd_config(section: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    return _normalize_cfd(section, config)


def normalize_testing_config(section: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    return _normalize_testing(section, config)


def normalize_coldflow_config(section: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    return normalize_hydraulic_validation_config(section, config)


def build_design_config(raw: Mapping[str, Any] | None = None) -> dict[str, Any]:
    config = deep_merge(DEFAULT_DESIGN_CONFIG, raw or {})
    config["uncertainty"] = {
        key: {"mode": spec.mode, "value": spec.value}
        for key, spec in _validate_uncertainty_section(config.get("uncertainty", {})).items()
    }
    config["constraints"] = deep_merge(_derived_default_constraints(config), config.get("constraints", {}))
    config["sensitivity_metrics"] = [str(metric) for metric in config.get("sensitivity_metrics", DEFAULT_SENSITIVITY_METRICS)]
    if not config["sensitivity_metrics"]:
        raise ValueError("At least one sensitivity metric is required.")
    config["geometry_policy"] = _normalize_geometry_policy(config.get("geometry_policy", {}))
    config["performance_lookup"] = _normalize_performance_lookup(config.get("performance_lookup", {}))
    config["internal_ballistics"] = _normalize_internal_ballistics(
        config.get("internal_ballistics", config.get("ballistics_1d", {})),
        config,
    )
    config["injector_design"] = _normalize_injector_design(
        config.get("injector_design", config.get("injector_geometry", {})),
        config,
    )
    config["hydraulic_validation"] = _normalize_hydraulic_validation(
        config.get("hydraulic_validation", config.get("coldflow", {})),
        config,
    )
    config["structural"] = _normalize_structural(config.get("structural", {}), config)
    config["thermal"] = _normalize_thermal(config.get("thermal", {}), config)
    config["nozzle_offdesign"] = _normalize_nozzle_offdesign(config.get("nozzle_offdesign", {}), config)
    config["cfd"] = _normalize_cfd(config.get("cfd", {}), config)
    config["testing"] = _normalize_testing(config.get("testing", {}), config)
    config["ballistics_1d"] = deepcopy(config["internal_ballistics"])
    config["injector_geometry"] = deepcopy(config["injector_design"])
    config["coldflow"] = deepcopy(config["hydraulic_validation"])
    config["nominal"]["blowdown"]["ui_mode"] = config["nominal"]["blowdown"].get("ui_mode", "advanced")
    config["nominal"]["blowdown"]["tank"]["initial_temp_k"] = float(
        config["nominal"]["performance"]["tank_temperature_k"]
    )
    return config


def load_design_config(path: str | Path) -> dict[str, Any]:
    return build_design_config(load_json(path))

