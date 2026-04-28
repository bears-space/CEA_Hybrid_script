"""Formatting helpers shared by CLI output, SVG output, and the UI API."""

from .variables import VARIABLE_LABELS


def float_tag(value):
    return f"{value:.4f}".rstrip("0").rstrip(".").replace(".", "p").replace("-", "m")


def metric_label(metric):
    return VARIABLE_LABELS.get(metric, metric.replace("_", " "))


def temperature_pair_label(fuel_temp_k, oxidizer_temp_k):
    return f"Fuel {fuel_temp_k:.0f} K | Ox {oxidizer_temp_k:.0f} K"

