"""Shared workflow constants for the modular design workflow layer."""

from pathlib import Path

OUTPUT_ROOT = Path("output")
RUNS_DIRNAME = "runs"
THERMOCHEMISTRY_DIRNAME = "thermochemistry"
PERFORMANCE_DIRNAME = "performance"
ANALYSIS_DIRNAME = "analysis"
GEOMETRY_DIRNAME = "geometry"
INTERNAL_BALLISTICS_DIRNAME = "internal_ballistics"
INJECTOR_DESIGN_DIRNAME = "injector_design"
HYDRAULIC_VALIDATION_DIRNAME = "hydraulic_validation"
STRUCTURAL_DIRNAME = "structural"
THERMAL_DIRNAME = "thermal"
NOZZLE_OFFDESIGN_DIRNAME = "nozzle_offdesign"
CFD_DIRNAME = "cfd"
TESTING_DIRNAME = "testing"
REPORTS_DIRNAME = "reports"

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
