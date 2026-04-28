"""Ignition and burn-window detection helpers."""

from __future__ import annotations

from typing import Mapping

import numpy as np


def detect_ignition_time_s(channels: Mapping[str, list[float]]) -> float | None:
    """Estimate ignition time from explicit ignition signal, pressure, or thrust."""

    time_s = np.asarray(channels.get("time_s", []), dtype=float)
    if time_s.size == 0:
        return None
    ignition_signal = np.asarray(channels.get("ignition_signal", []), dtype=float)
    if ignition_signal.size == time_s.size and ignition_signal.size:
        hits = np.flatnonzero(ignition_signal > 0.5)
        if hits.size:
            return float(time_s[hits[0]])
    for key in ("chamber_pressure_pa", "thrust_n"):
        values = np.asarray(channels.get(key, []), dtype=float)
        if values.size != time_s.size or values.size == 0:
            continue
        threshold = max(float(np.nanmax(values)) * 0.1, 1.0)
        hits = np.flatnonzero(values >= threshold)
        if hits.size:
            return float(time_s[hits[0]])
    return float(time_s[0])


def detect_burn_window(channels: Mapping[str, list[float]]) -> tuple[float | None, float | None]:
    """Estimate the active burn or flow window from pressure or thrust traces."""

    time_s = np.asarray(channels.get("time_s", []), dtype=float)
    if time_s.size == 0:
        return None, None
    for key in ("chamber_pressure_pa", "thrust_n", "mass_flow_kg_s"):
        values = np.asarray(channels.get(key, []), dtype=float)
        if values.size != time_s.size or values.size == 0:
            continue
        threshold = max(float(np.nanmax(values)) * 0.1, 1.0e-6)
        active = np.flatnonzero(values >= threshold)
        if active.size:
            return float(time_s[active[0]]), float(time_s[active[-1]])
    return float(time_s[0]), float(time_s[-1])
