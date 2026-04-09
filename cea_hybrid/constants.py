"""JSON-backed shared constants for the legacy CEA workflow."""

from __future__ import annotations

from project_data import load_project_constants


PLOT_COLORS = list(load_project_constants()["cea"]["plot_colors"])
