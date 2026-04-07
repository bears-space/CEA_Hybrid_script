"""Command-line entry point for batch sweep execution."""

from cea_hybrid.config import load_config
from cea_hybrid.constants import INPUTS_PATH
from cea_hybrid.outputs import write_outputs
from cea_hybrid.sweep import run_sweep


def main():
    config = load_config(INPUTS_PATH)
    output_dir = INPUTS_PATH.parent / config["output_dir"]
    sweep_results = run_sweep(config)

    print(f"Loaded inputs from {INPUTS_PATH}")
    print(f"Writing CSV outputs to {output_dir}")
    print(
        "Sweep sizes: "
        f"ABS={len(config['abs_volume_fractions'])}, "
        f"fuel T={len(config['fuel_temperatures_k'])}, "
        f"oxidizer T={len(config['oxidizer_temperatures_k'])}, "
        f"Ae/At={len(config['ae_at_values'])}, "
        f"O/F={len(config['of_values'])}"
    )
    print(f"Total combinations: {sweep_results['total_combinations']}")
    print(f"Compute backend: {sweep_results['backend']} ({sweep_results['cpu_workers']} worker(s))")

    plot_paths = write_outputs(output_dir, config, sweep_results)

    print(f"Converged cases: {len(sweep_results['cases'])}")
    print(f"Failed or unconverged cases: {len(sweep_results['failures'])}")
    print(f"Wrote {output_dir / 'all_cases.csv'}")
    print(f"Wrote {output_dir / 'failures.csv'}")
    if plot_paths:
        print(f"Wrote {len(plot_paths)} plot files to {output_dir / config['plots']['output_dir']}")
