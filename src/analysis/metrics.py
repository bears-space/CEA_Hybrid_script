"""Summary metric extraction for a single 0D or quasi-1D case history."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np


def _extended_values(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    return np.append(values, values[-1])


def _time_average(values: np.ndarray, time_s: np.ndarray, duration_s: float) -> float:
    if values.size == 0 or time_s.size == 0 or duration_s <= 0.0:
        return float("nan")
    return float(np.trapezoid(_extended_values(values), time_s) / duration_s)


def extract_case_metrics(result: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    requested_burn_time_s = float(config.get("nominal", config).get("blowdown", {}).get("simulation", {}).get("burn_time_s", 0.0))
    metrics: dict[str, Any] = {
        "status": result.get("status", "failed"),
        "stop_reason": result.get("stop_reason", "unknown"),
    }
    history = result.get("history") or {}
    axial_history = result.get("axial_history") or {}
    if not history:
        metrics.update(
            {
                "burn_time_actual_s": 0.0,
                "impulse_total_ns": 0.0,
                "thrust_avg_n": float("nan"),
                "thrust_peak_n": float("nan"),
                "pc_initial_bar": float("nan"),
                "pc_avg_bar": float("nan"),
                "pc_final_bar": float("nan"),
                "pc_peak_bar": float("nan"),
                "of_initial": float("nan"),
                "of_avg": float("nan"),
                "of_final": float("nan"),
                "mdot_ox_initial_kg_s": float("nan"),
                "mdot_ox_final_kg_s": float("nan"),
                "port_radius_final_mm": float("nan"),
                "fuel_mass_burned_kg": float("nan"),
                "oxidizer_mass_used_kg": float("nan"),
                "residual_ox_mass_kg": float("nan"),
                "remaining_oxidizer_reserve_kg": float("nan"),
                "burn_time_target_met": False,
                "geometry_valid": False,
                "injector_dp_ratio_min": float("nan"),
                "feed_dp_ratio_max": float("nan"),
                "injector_dominant_over_feed": False,
                "port_diameter_head_final_mm": float("nan"),
                "port_diameter_mid_final_mm": float("nan"),
                "port_diameter_tail_final_mm": float("nan"),
                "oxidizer_flux_max_kg_m2_s": float("nan"),
                "oxidizer_flux_min_kg_m2_s": float("nan"),
            }
        )
        return metrics

    time_s = np.asarray(history["integration_time_s"], dtype=float)
    duration_s = float(time_s[-1] - time_s[0]) if time_s.size else 0.0
    thrust_n = np.asarray(history["thrust_transient_actual_n"], dtype=float)
    thrust_vac_n = np.asarray(history.get("thrust_vac_n", []), dtype=float)
    pc_bar = np.asarray(history["pc_bar"], dtype=float)
    of_ratio = np.asarray(history["of_ratio"], dtype=float)
    mdot_ox = np.asarray(history["mdot_ox_kg_s"], dtype=float)
    mdot_f = np.asarray(history["mdot_f_kg_s"], dtype=float)
    mdot_total = np.asarray(history["mdot_total_kg_s"], dtype=float)
    port_radius_mm = np.asarray(history["port_radius_mm"], dtype=float)
    grain_web_remaining_mm = np.asarray(history.get("grain_web_remaining_mm", []), dtype=float)
    injector_dp_ratio = np.asarray(history.get("dp_injector_over_pc", []), dtype=float)
    feed_dp_ratio = np.asarray(history.get("dp_feed_over_pc", []), dtype=float)
    injector_to_feed_ratio = np.asarray(history.get("injector_to_feed_dp_ratio", []), dtype=float)
    isp_actual_s = np.asarray(history.get("isp_transient_s", history.get("isp_s", [])), dtype=float)
    initial_oxidizer_mass_kg = float(result["runtime"]["tank"].initial_mass_kg) if result.get("runtime") else float("nan")
    reserve_mass_kg = float(result.get("runtime", {}).get("tank", {}).reserve_mass_kg) if result.get("runtime") else float("nan")
    runtime_geometry_valid = bool(result.get("runtime", {}).get("derived", {}).get("geometry_valid", False))
    frozen_geometry = result.get("runtime", {}).get("frozen_geometry")
    geometry_valid = runtime_geometry_valid and bool(getattr(frozen_geometry, "geometry_valid", True))
    final_state = result.get("final_state")

    impulse_total_ns = float(np.trapezoid(_extended_values(thrust_n), time_s)) if time_s.size else 0.0
    oxidizer_mass_used_kg = float(np.trapezoid(_extended_values(mdot_ox), time_s)) if time_s.size else 0.0
    fuel_mass_burned_kg = float(np.trapezoid(_extended_values(mdot_f), time_s)) if time_s.size else 0.0
    residual_ox_mass_kg = float(max(initial_oxidizer_mass_kg - oxidizer_mass_used_kg, 0.0))
    remaining_oxidizer_reserve_kg = float(residual_ox_mass_kg - reserve_mass_kg) if np.isfinite(reserve_mass_kg) else float("nan")
    burn_time_target_met = duration_s >= max(requested_burn_time_s - 1e-9, 0.0)

    final_port_radius_head_mm = float(history["port_radius_head_mm"][-1]) if "port_radius_head_mm" in history else float("nan")
    final_port_radius_mid_mm = float(history["port_radius_mid_mm"][-1]) if "port_radius_mid_mm" in history else float("nan")
    final_port_radius_tail_mm = float(history["port_radius_tail_mm"][-1]) if "port_radius_tail_mm" in history else float("nan")
    if axial_history:
        final_port_radius_profile_mm = np.asarray(axial_history.get("port_radius_mm", []), dtype=float)
        if final_port_radius_profile_mm.size:
            final_profile_mm = final_port_radius_profile_mm[-1]
            head_index = 0
            mid_index = int(len(final_profile_mm) // 2)
            tail_index = int(len(final_profile_mm) - 1)
            final_port_radius_head_mm = float(final_profile_mm[head_index])
            final_port_radius_mid_mm = float(final_profile_mm[mid_index])
            final_port_radius_tail_mm = float(final_profile_mm[tail_index])
    elif final_state is not None and hasattr(final_state, "port_radii_m"):
        final_profile_mm = np.asarray(final_state.port_radii_m, dtype=float) * 1000.0
        if final_profile_mm.size:
            head_index = 0
            mid_index = int(len(final_profile_mm) // 2)
            tail_index = int(len(final_profile_mm) - 1)
            final_port_radius_head_mm = float(final_profile_mm[head_index])
            final_port_radius_mid_mm = float(final_profile_mm[mid_index])
            final_port_radius_tail_mm = float(final_profile_mm[tail_index])

    port_diameter_head_final_mm = 2.0 * final_port_radius_head_mm if np.isfinite(final_port_radius_head_mm) else float("nan")
    port_diameter_mid_final_mm = 2.0 * final_port_radius_mid_mm if np.isfinite(final_port_radius_mid_mm) else float("nan")
    port_diameter_tail_final_mm = 2.0 * final_port_radius_tail_mm if np.isfinite(final_port_radius_tail_mm) else float("nan")
    if np.isfinite(final_port_radius_mid_mm) and frozen_geometry is not None:
        grain_web_final_mm = max(float(frozen_geometry.grain_outer_radius_m) * 1000.0 - final_port_radius_mid_mm, 0.0)
    else:
        grain_web_final_mm = float(grain_web_remaining_mm[-1]) if grain_web_remaining_mm.size else float("nan")

    if axial_history:
        oxidizer_flux_field = np.asarray(axial_history.get("oxidizer_flux_kg_m2_s", []), dtype=float)
        oxidizer_flux_max_kg_m2_s = float(np.nanmax(oxidizer_flux_field)) if oxidizer_flux_field.size else float("nan")
        oxidizer_flux_min_kg_m2_s = float(np.nanmin(oxidizer_flux_field)) if oxidizer_flux_field.size else float("nan")
    else:
        oxidizer_flux_line = np.asarray(history.get("oxidizer_flux_kg_m2_s", []), dtype=float)
        oxidizer_flux_max_kg_m2_s = float(np.nanmax(oxidizer_flux_line)) if oxidizer_flux_line.size else float("nan")
        oxidizer_flux_min_kg_m2_s = float(np.nanmin(oxidizer_flux_line)) if oxidizer_flux_line.size else float("nan")

    metrics.update(
        {
            "burn_time_actual_s": duration_s,
            "burn_time_target_s": requested_burn_time_s,
            "burn_time_target_met": burn_time_target_met,
            "impulse_total_ns": impulse_total_ns,
            "thrust_avg_n": impulse_total_ns / duration_s if duration_s > 0.0 else float("nan"),
            "thrust_peak_n": float(np.max(thrust_n)),
            "thrust_vac_peak_n": float(np.max(thrust_vac_n)) if thrust_vac_n.size else float("nan"),
            "pc_initial_bar": float(pc_bar[0]),
            "pc_avg_bar": _time_average(pc_bar, time_s, duration_s),
            "pc_final_bar": float(pc_bar[-1]),
            "pc_peak_bar": float(np.max(pc_bar)),
            "of_initial": float(of_ratio[0]),
            "of_avg": _time_average(of_ratio, time_s, duration_s),
            "of_final": float(of_ratio[-1]),
            "mdot_ox_initial_kg_s": float(mdot_ox[0]),
            "mdot_ox_final_kg_s": float(mdot_ox[-1]),
            "mdot_total_initial_kg_s": float(mdot_total[0]),
            "mdot_total_final_kg_s": float(mdot_total[-1]),
            "isp_initial_s": float(isp_actual_s[0]) if isp_actual_s.size else float("nan"),
            "isp_final_s": float(isp_actual_s[-1]) if isp_actual_s.size else float("nan"),
            "isp_avg_s": _time_average(isp_actual_s, time_s, duration_s) if isp_actual_s.size else float("nan"),
            "port_radius_final_mm": final_port_radius_mid_mm,
            "grain_web_final_mm": grain_web_final_mm,
            "fuel_mass_burned_kg": fuel_mass_burned_kg,
            "oxidizer_mass_used_kg": oxidizer_mass_used_kg,
            "residual_ox_mass_kg": residual_ox_mass_kg,
            "remaining_oxidizer_reserve_kg": remaining_oxidizer_reserve_kg,
            "geometry_valid": geometry_valid,
            "injector_dp_ratio_min": float(np.nanmin(injector_dp_ratio)) if injector_dp_ratio.size else float("nan"),
            "feed_dp_ratio_max": float(np.nanmax(feed_dp_ratio)) if feed_dp_ratio.size else float("nan"),
            "injector_dominant_over_feed": bool(np.nanmin(injector_to_feed_ratio) >= 1.0) if injector_to_feed_ratio.size else False,
            "port_diameter_head_final_mm": port_diameter_head_final_mm,
            "port_diameter_mid_final_mm": port_diameter_mid_final_mm,
            "port_diameter_tail_final_mm": port_diameter_tail_final_mm,
            "oxidizer_flux_max_kg_m2_s": oxidizer_flux_max_kg_m2_s,
            "oxidizer_flux_min_kg_m2_s": oxidizer_flux_min_kg_m2_s,
        }
    )
    return metrics
