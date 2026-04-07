"""Compatibility facade plus CLI entry point for the sweep runner."""

from cea_hybrid.calculations import (
    abs_mass_fraction_from_volume_fraction,
    build_cea_objects,
    run_case,
)
from cea_hybrid.cli import main
from cea_hybrid.config import build_config, ensure_finite, expand_sweep_values, load_config, validate_config
from cea_hybrid.constants import CASE_FIELDS, DEFAULT_CPU_WORKERS, FAILURE_FIELDS, INPUTS_PATH
from cea_hybrid.labels import float_tag, metric_label, temperature_pair_label
from cea_hybrid.outputs import generate_plots, prepare_output_dir, write_csv, write_outputs
from cea_hybrid.sweep import (
    SweepCancelled,
    count_total_combinations,
    iter_case_inputs,
    resolve_cpu_workers,
    run_sweep,
)


__all__ = [
    "CASE_FIELDS",
    "DEFAULT_CPU_WORKERS",
    "FAILURE_FIELDS",
    "INPUTS_PATH",
    "SweepCancelled",
    "abs_mass_fraction_from_volume_fraction",
    "build_cea_objects",
    "build_config",
    "count_total_combinations",
    "ensure_finite",
    "expand_sweep_values",
    "float_tag",
    "generate_plots",
    "iter_case_inputs",
    "load_config",
    "main",
    "metric_label",
    "prepare_output_dir",
    "resolve_cpu_workers",
    "run_case",
    "run_sweep",
    "temperature_pair_label",
    "validate_config",
    "write_csv",
    "write_outputs",
]


if __name__ == "__main__":
    main()
