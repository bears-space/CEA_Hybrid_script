"""Summary metric extraction for a single 0D case history."""

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
    del config
    metrics: dict[str, Any] = {
        "status": result.get("status", "failed"),
        "stop_reason": result.get("stop_reason", "unknown"),
    }
    history = result.get("history") or {}
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
            }
        )
        return metrics

    time_s = np.asarray(history["integration_time_s"], dtype=float)
    duration_s = float(time_s[-1] - time_s[0]) if time_s.size else 0.0
    thrust_n = np.asarray(history["thrust_n"], dtype=float)
    pc_bar = np.asarray(history["pc_bar"], dtype=float)
    of_ratio = np.asarray(history["of_ratio"], dtype=float)
    mdot_ox = np.asarray(history["mdot_ox_kg_s"], dtype=float)
    mdot_f = np.asarray(history["mdot_f_kg_s"], dtype=float)
    ox_remaining = np.asarray(history["oxidizer_mass_remaining_kg"], dtype=float)
    port_radius_mm = np.asarray(history["port_radius_mm"], dtype=float)
    initial_oxidizer_mass_kg = float(result["runtime"]["tank"].initial_mass_kg) if result.get("runtime") else float("nan")

    impulse_total_ns = float(np.trapezoid(_extended_values(thrust_n), time_s)) if time_s.size else 0.0
    oxidizer_mass_used_kg = float(np.trapezoid(_extended_values(mdot_ox), time_s)) if time_s.size else 0.0
    fuel_mass_burned_kg = float(np.trapezoid(_extended_values(mdot_f), time_s)) if time_s.size else 0.0
    residual_ox_mass_kg = float(max(initial_oxidizer_mass_kg - oxidizer_mass_used_kg, 0.0))

    metrics.update(
        {
            "burn_time_actual_s": duration_s,
            "impulse_total_ns": impulse_total_ns,
            "thrust_avg_n": impulse_total_ns / duration_s if duration_s > 0.0 else float("nan"),
            "thrust_peak_n": float(np.max(thrust_n)),
            "pc_initial_bar": float(pc_bar[0]),
            "pc_avg_bar": _time_average(pc_bar, time_s, duration_s),
            "pc_final_bar": float(pc_bar[-1]),
            "pc_peak_bar": float(np.max(pc_bar)),
            "of_initial": float(of_ratio[0]),
            "of_avg": _time_average(of_ratio, time_s, duration_s),
            "of_final": float(of_ratio[-1]),
            "mdot_ox_initial_kg_s": float(mdot_ox[0]),
            "mdot_ox_final_kg_s": float(mdot_ox[-1]),
            "port_radius_final_mm": float(port_radius_mm[-1]),
            "fuel_mass_burned_kg": fuel_mass_burned_kg,
            "oxidizer_mass_used_kg": oxidizer_mass_used_kg,
            "residual_ox_mass_kg": residual_ox_mass_kg,
        }
    )
    return metrics
