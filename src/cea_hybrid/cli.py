"""Command-line entry point for batch sweep execution."""

import logging

from src.logging_utils import configure_logging

from .config import build_config
from .defaults import get_default_raw_config
from .outputs import write_outputs
from .sweep import run_sweep

LOGGER = logging.getLogger(__name__)


def main():
    configure_logging()
    config = build_config(get_default_raw_config())
    output_dir = config["output_dir"]
    sweep_results = run_sweep(config)

    LOGGER.info("Loaded built-in default configuration.")
    LOGGER.info("Writing CSV outputs to %s", output_dir)
    LOGGER.info(
        "Sweep sizes: "
        f"ABS={len(config['abs_volume_fractions'])}, "
        f"fuel T={len(config['fuel_temperatures_k'])}, "
        f"oxidizer T={len(config['oxidizer_temperatures_k'])}, "
        f"Ae/At={len(config['ae_at_values'])}, "
        f"O/F={len(config['of_values'])}"
    )
    LOGGER.info("Total combinations: %s", sweep_results["total_combinations"])
    LOGGER.info("Compute backend: %s (%s worker(s))", sweep_results["backend"], sweep_results["cpu_workers"])

    plot_paths = write_outputs(output_dir, config, sweep_results)

    LOGGER.info("Converged cases: %s", len(sweep_results["cases"]))
    LOGGER.info("Failed or unconverged cases: %s", len(sweep_results["failures"]))
    LOGGER.info("Wrote %s", output_dir / "all_cases.csv")
    LOGGER.info("Wrote %s", output_dir / "failures.csv")
    if plot_paths:
        LOGGER.info("Wrote %s plot files to %s", len(plot_paths), output_dir / config["plots"]["output_dir"])

