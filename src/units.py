"""Unit conversion helpers kept explicit for readability."""

from __future__ import annotations


def bar_to_pa(value_bar: float) -> float:
    return float(value_bar) * 1.0e5


def pa_to_bar(value_pa: float) -> float:
    return float(value_pa) / 1.0e5


def mm_to_m(value_mm: float) -> float:
    return float(value_mm) / 1000.0


def m_to_mm(value_m: float) -> float:
    return float(value_m) * 1000.0


def liters_to_m3(value_l: float) -> float:
    return float(value_l) / 1000.0


def m3_to_liters(value_m3: float) -> float:
    return float(value_m3) * 1000.0
