"""Shared constants and default values for the project."""

import os
from pathlib import Path

from cea_hybrid.variables import CASE_FIELDS, FAILURE_FIELDS, METRIC_OPTIONS


DEFAULT_CPU_WORKERS = os.cpu_count() or 1

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUTS_PATH = ROOT_DIR / "inputs.json"
UI_DIR = ROOT_DIR / "ui"

PLOT_COLORS = [
    "#0b7285",
    "#c92a2a",
    "#5f3dc4",
    "#2b8a3e",
    "#e67700",
    "#495057",
    "#1c7ed6",
    "#d6336c",
    "#5c940d",
    "#9c36b5",
]

ROOM_TEMPERATURE_K = 293.15
