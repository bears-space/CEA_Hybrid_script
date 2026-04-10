"""Comparison helpers between the baseline 0D solver and the Step 3 quasi-1D model."""

from __future__ import annotations

from typing import Any, Mapping


COMPARISON_METRICS = (
    "burn_time_actual_s",
    "impulse_total_ns",
    "thrust_avg_n",
    "thrust_peak_n",
    "pc_avg_bar",
    "pc_peak_bar",
    "of_avg",
    "port_radius_final_mm",
    "port_diameter_head_final_mm",
    "port_diameter_mid_final_mm",
    "port_diameter_tail_final_mm",
)


def compare_ballistics_metrics(zero_d_metrics: Mapping[str, Any], one_d_metrics: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metric in COMPARISON_METRICS:
        zero_d = zero_d_metrics.get(metric)
        one_d = one_d_metrics.get(metric)
        if isinstance(zero_d, (int, float)) and isinstance(one_d, (int, float)):
            delta_abs = float(one_d - zero_d)
            delta_rel = delta_abs / abs(float(zero_d)) if float(zero_d) != 0.0 else None
        else:
            delta_abs = None
            delta_rel = None
        rows.append(
            {
                "metric": metric,
                "zero_d": zero_d,
                "one_d": one_d,
                "delta_abs": delta_abs,
                "delta_rel": delta_rel,
            }
        )
    return rows


def comparison_summary(zero_d_metrics: Mapping[str, Any], one_d_metrics: Mapping[str, Any]) -> dict[str, Any]:
    rows = compare_ballistics_metrics(zero_d_metrics, one_d_metrics)
    keyed = {row["metric"]: row for row in rows}
    return {
        "rows": rows,
        "impulse_delta_percent": None
        if keyed["impulse_total_ns"]["delta_rel"] is None
        else 100.0 * keyed["impulse_total_ns"]["delta_rel"],
        "burn_time_delta_percent": None
        if keyed["burn_time_actual_s"]["delta_rel"] is None
        else 100.0 * keyed["burn_time_actual_s"]["delta_rel"],
        "thrust_avg_delta_percent": None
        if keyed["thrust_avg_n"]["delta_rel"] is None
        else 100.0 * keyed["thrust_avg_n"]["delta_rel"],
    }
