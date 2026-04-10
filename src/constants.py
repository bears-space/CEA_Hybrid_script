"""Shared workflow constants for the modular design study layer."""

from pathlib import Path

OUTPUT_ROOT = Path("output")
NOMINAL_DIRNAME = "nominal"
SENSITIVITY_DIRNAME = "sensitivity"
CORNERS_DIRNAME = "corners"
CEA_DIRNAME = "cea"
GEOMETRY_DIRNAME = "geometry"
BALLISTICS_1D_DIRNAME = "ballistics_1d"

DEFAULT_SENSITIVITY_METRICS = [
    "pc_avg_bar",
    "pc_peak_bar",
    "thrust_avg_n",
    "impulse_total_ns",
    "of_avg",
]

SUPPORTED_UNCERTAINTY_PARAMETERS = {
    "tank_temperature_k",
    "fill_fraction",
    "usable_ox_fraction",
    "injector_cd",
    "regression_a",
    "regression_n",
    "cstar_efficiency",
    "cf_efficiency",
    "usable_fuel_fraction",
    "injector_dp_fraction",
    "line_loss_multiplier",
    "nozzle_discharge_factor",
}
