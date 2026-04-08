"""UI-facing config, preview, and response builders for the blowdown model."""

from __future__ import annotations

from cea_hybrid.labels import metric_label
from cea_hybrid.variables import CASE_FIELDS

from blowdown_hybrid.calculations import build_runtime_inputs
from blowdown_hybrid.config import build_config
from blowdown_hybrid.constants import (
    INJECTOR_DELTA_P_MODE_EXPLICIT,
    MODEL_ASSUMPTIONS,
    STOP_REASON_LABELS,
    UI_MODE_ADVANCED,
    UI_MODE_BASIC,
)
from blowdown_hybrid.variables import variable_label


def _points(xs, ys):
    return [{"x": float(x), "y": float(y)} for x, y in zip(xs, ys)]


def _field_list(values):
    return [{"key": key, "label": variable_label(key), "value": value} for key, value in values]


def _seed_case_fields(case):
    keys = [
        "target_thrust_n",
        "isp_s",
        "thrust_sl_n",
        "of",
        "pc_bar",
        "cstar_mps",
        "fuel_temp_k",
        "oxidizer_temp_k",
        "abs_vol_frac",
    ]
    return [{"key": key, "label": metric_label(key), "value": case[key]} for key in keys if key in case]


def _preview_fields(runtime):
    values = [
        ("seed_target_thrust_n", runtime["derived"]["seed_target_thrust_n"]),
        ("seed_isp_s", runtime["derived"]["seed_isp_s"]),
        ("seed_of_ratio", runtime["derived"]["seed_of_ratio"]),
        ("seed_pc_bar", runtime["derived"]["seed_pc_bar"]),
        ("seed_oxidizer_temp_k", runtime["derived"]["seed_oxidizer_temp_k"]),
        ("seed_fuel_temp_k", runtime["derived"]["seed_fuel_temp_k"]),
        ("seed_abs_volume_fraction", runtime["derived"]["seed_abs_volume_fraction"]),
        ("seed_abs_mass_fraction", runtime["derived"]["seed_abs_mass_fraction"]),
        ("target_mdot_total_kg_s", runtime["derived"]["target_mdot_total_kg_s"]),
        ("target_mdot_ox_kg_s", runtime["derived"]["target_mdot_ox_kg_s"]),
        ("target_mdot_f_kg_s", runtime["derived"]["target_mdot_f_kg_s"]),
        ("required_oxidizer_mass_kg", runtime["derived"]["required_oxidizer_mass_kg"]),
        ("loaded_oxidizer_mass_kg", runtime["derived"]["loaded_oxidizer_mass_kg"]),
        ("required_fuel_mass_kg", runtime["derived"]["required_fuel_mass_kg"]),
        ("loaded_fuel_mass_kg", runtime["derived"]["loaded_fuel_mass_kg"]),
        ("fuel_density_kg_m3", runtime["derived"]["fuel_density_kg_m3"]),
        ("tank_initial_fill_fraction", runtime["derived"]["tank_initial_fill_fraction"]),
        ("tank_usable_oxidizer_fraction", runtime["derived"]["tank_usable_oxidizer_fraction"]),
        ("tank_oxidizer_liquid_volume_l", runtime["derived"]["tank_oxidizer_liquid_volume_l"]),
        ("tank_volume_l", runtime["derived"]["tank_volume_l"]),
        ("tank_initial_mass_kg", runtime["derived"]["tank_initial_mass_kg"]),
        ("tank_initial_temp_k", runtime["derived"]["tank_initial_temp_k"]),
        ("target_initial_gox_kg_m2_s", runtime["derived"]["target_initial_gox_kg_m2_s"]),
        ("initial_port_area_mm2", runtime["derived"]["initial_port_area_mm2"]),
        ("initial_port_radius_mm", runtime["derived"]["initial_port_radius_mm"]),
        ("initial_regression_rate_mm_s", runtime["derived"]["initial_regression_rate_mm_s"]),
        ("grain_length_m", runtime["derived"]["grain_length_m"]),
        ("grain_outer_radius_mm", runtime["derived"]["grain_outer_radius_mm"]),
        ("injector_cd", runtime["derived"]["injector_cd"]),
        ("injector_hole_count", runtime["derived"]["injector_hole_count"]),
        ("injector_delta_p_bar", runtime["derived"]["injector_delta_p_bar"]),
        ("injector_total_area_mm2", runtime["derived"]["injector_total_area_mm2"]),
        ("injector_area_per_hole_mm2", runtime["derived"]["injector_area_per_hole_mm2"]),
        ("injector_hole_diameter_mm", runtime["derived"]["injector_hole_diameter_mm"]),
    ]
    return _field_list(values)


def _override_fields(config, runtime):
    values = [
        ("ui_mode", config["ui_mode"]),
        ("tank_mass_volume_source", runtime["derived"]["tank_mass_volume_source"]),
        ("injector_total_area_source", runtime["derived"]["injector_total_area_source"]),
        ("initial_port_source", runtime["derived"]["initial_port_source"]),
        ("grain_length_source", runtime["derived"]["grain_length_source"]),
        ("outer_radius_source", runtime["derived"]["outer_radius_source"]),
    ]
    return _field_list(values)


def build_default_ui_config(raw):
    config = build_config(raw.get("blowdown", {}))
    return {
        "auto_run_after_cea": config["auto_run_after_cea"],
        "ui_mode": config["ui_mode"],
        "seed_case": config["seed_case"],
        "tank": {
            "volume_l": config["tank"]["volume_m3"] * 1000.0,
            "initial_mass_kg": config["tank"]["initial_mass_kg"],
            "initial_temp_k": config["tank"]["initial_temp_k"],
            "usable_oxidizer_fraction": config["tank"]["usable_oxidizer_fraction"],
            "initial_fill_fraction": config["tank"]["initial_fill_fraction"],
            "override_mass_volume": config["tank"]["override_mass_volume"],
        },
        "feed": {
            "line_id_mm": config["feed"]["line_id_m"] * 1e3,
            "line_length_m": config["feed"]["line_length_m"],
            "friction_factor": config["feed"]["friction_factor"],
            "minor_loss_k_total": config["feed"]["minor_loss_k_total"],
        },
        "injector": {
            "cd": config["injector"]["cd"],
            "hole_count": config["injector"]["hole_count"],
            "total_area_mm2": config["injector"]["total_area_m2"] * 1e6,
            "override_total_area": config["injector"]["override_total_area"],
            "delta_p_mode": config["injector"]["delta_p_mode"],
            "delta_p_pa": config["injector"]["delta_p_pa"],
            "delta_p_fraction_of_pc": config["injector"]["delta_p_fraction_of_pc"],
        },
        "grain": {
            "abs_density_kg_m3": config["grain"]["abs_density_kg_m3"],
            "paraffin_density_kg_m3": config["grain"]["paraffin_density_kg_m3"],
            "a_reg_si": config["grain"]["a_reg_si"],
            "n_reg": config["grain"]["n_reg"],
            "port_count": config["grain"]["port_count"],
            "target_initial_gox_kg_m2_s": config["grain"]["target_initial_gox_kg_m2_s"],
            "initial_port_radius_mm": config["grain"]["initial_port_radius_m"] * 1e3,
            "grain_length_m": config["grain"]["grain_length_m"],
            "outer_radius_mm": None if config["grain"]["outer_radius_m"] is None else config["grain"]["outer_radius_m"] * 1e3,
            "fuel_usable_fraction": config["grain"]["fuel_usable_fraction"],
            "override_initial_port_radius": config["grain"]["override_initial_port_radius"],
            "override_grain_length": config["grain"]["override_grain_length"],
            "override_outer_radius": config["grain"]["override_outer_radius"],
        },
        "simulation": {
            "dt_s": config["simulation"]["dt_s"],
            "burn_time_s": config["simulation"]["burn_time_s"],
            "ambient_pressure_bar": config["simulation"]["ambient_pressure_pa"] / 1e5,
            "max_inner_iterations": config["simulation"]["max_inner_iterations"],
            "relaxation": config["simulation"]["relaxation"],
            "relative_tolerance": config["simulation"]["relative_tolerance"],
            "stop_when_tank_quality_exceeds": config["simulation"]["stop_when_tank_quality_exceeds"],
        },
    }


def build_config_from_payload(payload):
    return build_config(
        {
            "auto_run_after_cea": bool(payload.get("auto_run_after_cea", True)),
            "ui_mode": payload.get("ui_mode", UI_MODE_BASIC),
            "seed_case": payload.get("seed_case", "highest_isp"),
            "tank": {
                "volume_m3": float(payload["tank"]["volume_l"]) / 1000.0,
                "initial_mass_kg": float(payload["tank"]["initial_mass_kg"]),
                "initial_temp_k": float(payload["tank"]["initial_temp_k"]),
                "usable_oxidizer_fraction": float(payload["tank"]["usable_oxidizer_fraction"]),
                "initial_fill_fraction": float(payload["tank"]["initial_fill_fraction"]),
                "override_mass_volume": bool(payload["tank"].get("override_mass_volume", False)),
            },
            "feed": {
                "line_id_m": float(payload["feed"]["line_id_mm"]) / 1000.0,
                "line_length_m": float(payload["feed"]["line_length_m"]),
                "friction_factor": float(payload["feed"]["friction_factor"]),
                "minor_loss_k_total": float(payload["feed"]["minor_loss_k_total"]),
            },
            "injector": {
                "cd": float(payload["injector"]["cd"]),
                "hole_count": int(payload["injector"]["hole_count"]),
                "total_area_m2": float(payload["injector"]["total_area_mm2"]) / 1e6,
                "override_total_area": bool(payload["injector"].get("override_total_area", False)),
                "delta_p_mode": payload["injector"]["delta_p_mode"],
                "delta_p_pa": float(payload["injector"]["delta_p_pa"]),
                "delta_p_fraction_of_pc": float(payload["injector"]["delta_p_fraction_of_pc"]),
            },
            "grain": {
                "abs_density_kg_m3": float(payload["grain"]["abs_density_kg_m3"]),
                "paraffin_density_kg_m3": float(payload["grain"]["paraffin_density_kg_m3"]),
                "a_reg_si": float(payload["grain"]["a_reg_si"]),
                "n_reg": float(payload["grain"]["n_reg"]),
                "port_count": int(payload["grain"]["port_count"]),
                "target_initial_gox_kg_m2_s": float(payload["grain"]["target_initial_gox_kg_m2_s"]),
                "initial_port_radius_m": float(payload["grain"]["initial_port_radius_mm"]) / 1000.0,
                "grain_length_m": float(payload["grain"]["grain_length_m"]),
                "outer_radius_m": (
                    None
                    if payload["grain"].get("outer_radius_mm") in {None, ""}
                    else float(payload["grain"]["outer_radius_mm"]) / 1000.0
                ),
                "fuel_usable_fraction": float(payload["grain"]["fuel_usable_fraction"]),
                "override_initial_port_radius": bool(payload["grain"].get("override_initial_port_radius", False)),
                "override_grain_length": bool(payload["grain"].get("override_grain_length", False)),
                "override_outer_radius": bool(payload["grain"].get("override_outer_radius", False)),
            },
            "simulation": {
                "dt_s": float(payload["simulation"]["dt_s"]),
                "burn_time_s": float(payload["simulation"]["burn_time_s"]),
                "ambient_pressure_pa": float(payload["simulation"]["ambient_pressure_bar"]) * 1e5,
                "max_inner_iterations": int(payload["simulation"]["max_inner_iterations"]),
                "relaxation": float(payload["simulation"]["relaxation"]),
                "relative_tolerance": float(payload["simulation"]["relative_tolerance"]),
                "stop_when_tank_quality_exceeds": float(payload["simulation"]["stop_when_tank_quality_exceeds"]),
            },
        }
    )


def build_pending_response(config, seed_case, status, message, error=None):
    return {
        "status": status,
        "message": message,
        "error": error,
        "auto_run_after_cea": config["auto_run_after_cea"],
        "ui_mode": config["ui_mode"],
        "seed_case_source": config["seed_case"],
        "seed_case_source_label": "Highest Isp CEA Case",
        "seed_case": {key: seed_case[key] for key in CASE_FIELDS if key in seed_case},
        "seed_case_fields": _seed_case_fields(seed_case),
        "controls": build_default_ui_config({"blowdown": config}),
        "assumptions": MODEL_ASSUMPTIONS,
    }


def build_not_run_response(config, seed_case):
    return build_pending_response(
        config,
        seed_case,
        status="not_run",
        message="Automatic preliminary 0D blowdown execution is disabled. Run the 0D blowdown model manually when needed.",
    )


def build_running_response(config, seed_case):
    return build_pending_response(
        config,
        seed_case,
        status="running",
        message="Running the preliminary 0D blowdown model from the highest-Isp CEA case...",
    )


def build_error_response(config, seed_case, error_message):
    return build_pending_response(
        config,
        seed_case,
        status="error",
        message="The preliminary 0D blowdown model failed.",
        error=error_message,
    )


def build_preview_response(config, seed_case):
    try:
        runtime = build_runtime_inputs(config, seed_case)
    except Exception as exc:
        return {
            "status": "error",
            "message": "Unable to update first-pass sizing preview.",
            "error": str(exc),
            "controls": build_default_ui_config({"blowdown": config}),
        }

    controls = build_default_ui_config({"blowdown": config})
    return {
        "status": "ready",
        "message": (
            "Basic mode uses the latest completed highest-Isp CEA case for Isp, O/F, c*, temperatures, and ABS volume fraction."
            if config["ui_mode"] == UI_MODE_BASIC
            else "Advanced mode is active. Manual overrides marked as overridden take precedence over the first-pass estimates."
        ),
        "error": None,
        "controls": controls,
        "seed_case_source_label": "Highest Isp CEA Case",
        "seed_case_fields": _seed_case_fields(seed_case),
        "preview_fields": _preview_fields(runtime),
        "override_fields": _override_fields(config, runtime),
    }


def build_ui_response(config, seed_case, runtime, runtime_seconds):
    history = runtime["history"]
    time_s = history["time_s"]
    initial_index = 0
    final_index = -1

    summary_values = [
        ("stop_reason", STOP_REASON_LABELS.get(runtime["stop_reason"], runtime["stop_reason"])),
        ("simulated_time_s", float(time_s[-1])),
        ("step_count", int(runtime["step_count"])),
        ("initial_tank_pressure_bar", float(history["tank_p_pa"][0] / 1e5)),
        ("final_tank_pressure_bar", float(history["tank_p_pa"][-1] / 1e5)),
        ("initial_chamber_pressure_bar", float(history["pc_pa"][0] / 1e5)),
        ("final_chamber_pressure_bar", float(history["pc_pa"][-1] / 1e5)),
        ("initial_thrust_n", float(history["thrust_n"][0])),
        ("final_thrust_n", float(history["thrust_n"][-1])),
        ("initial_isp_s", float(history["isp_s"][0])),
        ("final_isp_s", float(history["isp_s"][-1])),
        ("initial_of_ratio", float(history["of_ratio"][0])),
        ("final_of_ratio", float(history["of_ratio"][-1])),
        ("initial_port_diameter_mm", float(2.0 * history["port_radius_m"][0] * 1e3)),
        ("final_port_diameter_mm", float(2.0 * history["port_radius_m"][-1] * 1e3)),
        ("initial_tank_quality", float(history["tank_quality"][0])),
        ("final_tank_quality", float(history["tank_quality"][-1])),
    ]

    derived_values = [
        ("model_name", runtime["derived"]["model_name"]),
        ("ui_mode", runtime["derived"]["ui_mode"]),
        ("seed_target_thrust_n", runtime["derived"]["seed_target_thrust_n"]),
        ("seed_isp_s", runtime["derived"]["seed_isp_s"]),
        ("seed_of_ratio", runtime["derived"]["seed_of_ratio"]),
        ("seed_pc_bar", runtime["derived"]["seed_pc_bar"]),
        ("seed_oxidizer_temp_k", runtime["derived"]["seed_oxidizer_temp_k"]),
        ("seed_fuel_temp_k", runtime["derived"]["seed_fuel_temp_k"]),
        ("seed_abs_volume_fraction", runtime["derived"]["seed_abs_volume_fraction"]),
        ("seed_abs_mass_fraction", runtime["derived"]["seed_abs_mass_fraction"]),
        ("target_mdot_total_kg_s", runtime["derived"]["target_mdot_total_kg_s"]),
        ("target_mdot_ox_kg_s", runtime["derived"]["target_mdot_ox_kg_s"]),
        ("target_mdot_f_kg_s", runtime["derived"]["target_mdot_f_kg_s"]),
        ("target_of_ratio", runtime["derived"]["target_of_ratio"]),
        ("target_pc_bar", runtime["derived"]["target_pc_bar"]),
        ("required_oxidizer_mass_kg", runtime["derived"]["required_oxidizer_mass_kg"]),
        ("loaded_oxidizer_mass_kg", runtime["derived"]["loaded_oxidizer_mass_kg"]),
        ("required_fuel_mass_kg", runtime["derived"]["required_fuel_mass_kg"]),
        ("loaded_fuel_mass_kg", runtime["derived"]["loaded_fuel_mass_kg"]),
        ("fuel_density_kg_m3", runtime["derived"]["fuel_density_kg_m3"]),
        ("tank_oxidizer_liquid_volume_l", runtime["derived"]["tank_oxidizer_liquid_volume_l"]),
        ("tank_volume_l", runtime["derived"]["tank_volume_l"]),
        ("tank_initial_mass_kg", runtime["derived"]["tank_initial_mass_kg"]),
        ("tank_initial_temp_k", runtime["derived"]["tank_initial_temp_k"]),
        ("target_initial_gox_kg_m2_s", runtime["derived"]["target_initial_gox_kg_m2_s"]),
        ("initial_port_area_mm2", runtime["derived"]["initial_port_area_mm2"]),
        ("initial_port_radius_mm", runtime["derived"]["initial_port_radius_mm"]),
        ("initial_regression_rate_mm_s", runtime["derived"]["initial_regression_rate_mm_s"]),
        ("grain_length_m", runtime["derived"]["grain_length_m"]),
        ("grain_outer_radius_mm", runtime["derived"]["grain_outer_radius_mm"]),
    ]

    injector_estimate_values = [
        ("injector_cd", runtime["derived"]["injector_cd"]),
        ("injector_hole_count", runtime["derived"]["injector_hole_count"]),
        ("injector_delta_p_mode", runtime["derived"]["injector_delta_p_mode"]),
        ("injector_delta_p_bar", runtime["derived"]["injector_delta_p_bar"]),
        ("injector_total_area_mm2", runtime["derived"]["injector_total_area_mm2"]),
        ("injector_area_per_hole_mm2", runtime["derived"]["injector_area_per_hole_mm2"]),
        ("injector_hole_diameter_mm", runtime["derived"]["injector_hole_diameter_mm"]),
        ("nozzle_throat_area_mm2", runtime["derived"]["nozzle_throat_area_mm2"]),
        ("nozzle_exit_area_mm2", runtime["derived"]["nozzle_exit_area_mm2"]),
        ("nozzle_cstar_mps", runtime["derived"]["nozzle_cstar_mps"]),
        ("nozzle_cf", runtime["derived"]["nozzle_cf"]),
        ("design_tank_pressure_bar", runtime["derived"]["design_tank_pressure_bar"]),
        ("design_liquid_density_kg_m3", runtime["derived"]["design_liquid_density_kg_m3"]),
        ("design_injector_inlet_pressure_bar", runtime["derived"]["design_injector_inlet_pressure_bar"]),
        ("design_feed_pressure_drop_bar", runtime["derived"]["design_feed_pressure_drop_bar"]),
        ("design_injector_delta_p_bar", runtime["derived"]["design_injector_delta_p_bar"]),
    ]

    override_values = [
        ("tank_mass_volume_source", runtime["derived"]["tank_mass_volume_source"]),
        ("injector_total_area_source", runtime["derived"]["injector_total_area_source"]),
        ("initial_port_source", runtime["derived"]["initial_port_source"]),
        ("grain_length_source", runtime["derived"]["grain_length_source"]),
        ("outer_radius_source", runtime["derived"]["outer_radius_source"]),
    ]

    initial_state_values = [
        ("initial_tank_pressure_bar", float(history["tank_p_pa"][initial_index] / 1e5)),
        ("initial_tank_temperature_k", float(history["tank_T_k"][initial_index])),
        ("initial_tank_quality", float(history["tank_quality"][initial_index])),
        ("initial_liquid_density_kg_m3", float(history["rho_liq_kg_m3"][initial_index])),
        ("initial_injector_inlet_pressure_bar", float(history["p_inj_in_pa"][initial_index] / 1e5)),
        ("initial_feed_pressure_drop_bar", float(history["dp_feed_pa"][initial_index] / 1e5)),
        ("initial_injector_delta_p_bar", float(history["dp_inj_pa"][initial_index] / 1e5)),
        ("initial_chamber_pressure_bar", float(history["pc_pa"][initial_index] / 1e5)),
        ("initial_mdot_ox_kg_s", float(history["mdot_ox_kg_s"][initial_index])),
        ("initial_mdot_f_kg_s", float(history["mdot_f_kg_s"][initial_index])),
        ("initial_mdot_total_kg_s", float(history["mdot_total_kg_s"][initial_index])),
        ("initial_of_ratio", float(history["of_ratio"][initial_index])),
        ("initial_oxidizer_flux_kg_m2_s", float(history["Gox_kg_m2_s"][initial_index])),
        ("initial_regression_rate_mm_s", float(history["rdot_m_s"][initial_index] * 1e3)),
        ("initial_thrust_n", float(history["thrust_n"][initial_index])),
        ("initial_isp_s", float(history["isp_s"][initial_index])),
        ("initial_port_diameter_mm", float(2.0 * history["port_radius_m"][initial_index] * 1e3)),
    ]

    final_state_values = [
        ("final_tank_pressure_bar", float(history["tank_p_pa"][final_index] / 1e5)),
        ("final_tank_temperature_k", float(history["tank_T_k"][final_index])),
        ("final_tank_quality", float(history["tank_quality"][final_index])),
        ("final_liquid_density_kg_m3", float(history["rho_liq_kg_m3"][final_index])),
        ("final_injector_inlet_pressure_bar", float(history["p_inj_in_pa"][final_index] / 1e5)),
        ("final_feed_pressure_drop_bar", float(history["dp_feed_pa"][final_index] / 1e5)),
        ("final_injector_delta_p_bar", float(history["dp_inj_pa"][final_index] / 1e5)),
        ("final_chamber_pressure_bar", float(history["pc_pa"][final_index] / 1e5)),
        ("final_mdot_ox_kg_s", float(history["mdot_ox_kg_s"][final_index])),
        ("final_mdot_f_kg_s", float(history["mdot_f_kg_s"][final_index])),
        ("final_mdot_total_kg_s", float(history["mdot_total_kg_s"][final_index])),
        ("final_of_ratio", float(history["of_ratio"][final_index])),
        ("final_oxidizer_flux_kg_m2_s", float(history["Gox_kg_m2_s"][final_index])),
        ("final_regression_rate_mm_s", float(history["rdot_m_s"][final_index] * 1e3)),
        ("final_thrust_n", float(history["thrust_n"][final_index])),
        ("final_isp_s", float(history["isp_s"][final_index])),
        ("final_port_diameter_mm", float(2.0 * history["port_radius_m"][final_index] * 1e3)),
    ]

    return {
        "status": "completed",
        "message": "Preliminary 0D blowdown model complete.",
        "error": None,
        "auto_run_after_cea": config["auto_run_after_cea"],
        "ui_mode": config["ui_mode"],
        "seed_case_source": config["seed_case"],
        "seed_case_source_label": "Highest Isp CEA Case",
        "runtime_seconds": runtime_seconds,
        "seed_case": {key: seed_case[key] for key in CASE_FIELDS if key in seed_case},
        "seed_case_fields": _seed_case_fields(seed_case),
        "controls": build_default_ui_config({"blowdown": config}),
        "summary_fields": _field_list(summary_values),
        "derived_fields": _field_list(derived_values),
        "injector_estimate_fields": _field_list(injector_estimate_values),
        "override_fields": _field_list(override_values),
        "initial_state_fields": _field_list(initial_state_values),
        "final_state_fields": _field_list(final_state_values),
        "assumptions": MODEL_ASSUMPTIONS,
        "charts": {
            "pressure_vs_time": [
                {"label": "Tank Pressure [bar]", "points": _points(time_s, history["tank_p_pa"] / 1e5)},
                {"label": "Injector Inlet Pressure [bar]", "points": _points(time_s, history["p_inj_in_pa"] / 1e5)},
                {"label": "Chamber Pressure [bar]", "points": _points(time_s, history["pc_pa"] / 1e5)},
            ],
            "mass_flow_vs_time": [
                {"label": "Oxidizer Flow [kg/s]", "points": _points(time_s, history["mdot_ox_kg_s"])},
                {"label": "Fuel Flow [kg/s]", "points": _points(time_s, history["mdot_f_kg_s"])},
                {"label": "Total Flow [kg/s]", "points": _points(time_s, history["mdot_total_kg_s"])},
            ],
            "thrust_vs_time": [
                {"label": "Thrust [N]", "points": _points(time_s, history["thrust_n"])},
            ],
            "state_vs_time": [
                {"label": "O/F [-]", "points": _points(time_s, history["of_ratio"])},
                {"label": "Tank Quality [-]", "points": _points(time_s, history["tank_quality"])},
            ],
        },
    }
