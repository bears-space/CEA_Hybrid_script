"""Reduced-order feature extraction from cleaned test datasets."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from src.testing.test_types import TestDataset, TestRunSummary


def _integral(values: np.ndarray, time_s: np.ndarray) -> float | None:
    if values.size == 0 or time_s.size == 0:
        return None
    if values.size != time_s.size:
        size = min(values.size, time_s.size)
        values = values[:size]
        time_s = time_s[:size]
    return float(np.trapezoid(values, time_s))


def summarize_test_dataset(dataset: TestDataset) -> TestRunSummary:
    """Compute high-value summary metrics from a cleaned test dataset."""

    channels = dataset.cleaned_time_series_channels or dataset.time_series_channels
    time_s = np.asarray(channels.get("time_s", []), dtype=float)
    chamber_pressure = np.asarray(channels.get("chamber_pressure_pa", []), dtype=float)
    thrust_n = np.asarray(channels.get("thrust_n", []), dtype=float)
    mdot_ox = np.asarray(channels.get("oxidizer_mass_flow_kg_s", channels.get("mass_flow_kg_s", [])), dtype=float)
    mdot_f = np.asarray(channels.get("fuel_mass_flow_kg_s", []), dtype=float)
    tank_mass = np.asarray(channels.get("tank_mass_kg", []), dtype=float)
    burn_duration_s = float(max(time_s[-1] - time_s[0], 0.0)) if time_s.size else 0.0
    impulse = _integral(thrust_n, time_s)
    oxidizer_used = _integral(mdot_ox, time_s)
    fuel_used = _integral(mdot_f, time_s)
    if fuel_used is None:
        fuel_used = dataset.metadata.get("fuel_used_kg")
    if oxidizer_used is None and tank_mass.size == time_s.size and tank_mass.size > 1:
        oxidizer_used = float(max(tank_mass[0] - tank_mass[-1], 0.0))
    avg_pressure = float(np.nanmean(chamber_pressure)) if chamber_pressure.size else None
    avg_thrust = float(np.nanmean(thrust_n)) if thrust_n.size else None
    peak_pressure = float(np.nanmax(chamber_pressure)) if chamber_pressure.size else None
    peak_thrust = float(np.nanmax(thrust_n)) if thrust_n.size else None
    ignition_time_s = dataset.metadata.get("ignition_time_s")
    pressure_rise_time_s = None
    if chamber_pressure.size and time_s.size == chamber_pressure.size:
        threshold_10 = float(np.nanmax(chamber_pressure)) * 0.1
        threshold_90 = float(np.nanmax(chamber_pressure)) * 0.9
        above_10 = np.flatnonzero(chamber_pressure >= threshold_10)
        above_90 = np.flatnonzero(chamber_pressure >= threshold_90)
        if above_10.size and above_90.size:
            pressure_rise_time_s = float(max(time_s[above_90[0]] - time_s[above_10[0]], 0.0))
    shutdown_tail_time_s = None
    if thrust_n.size and time_s.size == thrust_n.size:
        tail_threshold = float(np.nanmax(thrust_n)) * 0.1
        active = np.flatnonzero(thrust_n >= tail_threshold)
        if active.size:
            shutdown_tail_time_s = float(max(time_s[-1] - time_s[active[-1]], 0.0))

    return TestRunSummary(
        run_id=dataset.run_id,
        article_id=dataset.article_id,
        stage_name=dataset.stage_name,
        start_time=dataset.metadata.get("start_time"),
        achieved_burn_time_s=burn_duration_s,
        peak_chamber_pressure_pa=peak_pressure,
        average_chamber_pressure_pa=avg_pressure,
        peak_thrust_n=peak_thrust,
        average_thrust_n=avg_thrust,
        total_impulse_ns=impulse,
        oxidizer_used_kg=float(oxidizer_used) if oxidizer_used is not None and math.isfinite(float(oxidizer_used)) else None,
        fuel_used_kg=float(fuel_used) if fuel_used is not None and math.isfinite(float(fuel_used)) else None,
        ignition_time_s=float(ignition_time_s) if ignition_time_s is not None else None,
        stop_reason=str(dataset.metadata.get("stop_reason")) if dataset.metadata.get("stop_reason") is not None else None,
        anomalies=list(dataset.metadata.get("anomalies", [])),
        derived_metrics={
            "pressure_rise_time_s": pressure_rise_time_s,
            "shutdown_tail_time_s": shutdown_tail_time_s,
        },
        notes=["Derived from cleaned test dataset using first-pass feature extraction only."],
    )
