# CEA Hybrid Script

This project runs NASA CEA-based performance calculations for an N2O and paraffin hybrid rocket engine with ABS structure represented by a styrene/butadiene surrogate blend. The project includes both a sweep script and a local browser UI for running parameter studies and inspecting raw CEA result points.

## What It Does

- Evaluates N2O/paraffin/ABS-structure hybrid rocket performance with the `cea` Python package
- Sweeps across user-defined `O/F` and `Ae/At` values, with configurable fuel temperature, oxidizer temperature, and infill target
- Writes full raw-case CSV data and failed/unconverged cases
- Generates organized SVG temperature-pair dashboards automatically
- Reports NASA CEA outputs plus a minimal post-CEA nozzle sizing layer for target thrust, mass flow, choked throat area, exit area, and circular-equivalent throat/exit diameters

## Project Files

- `main.py`: thin command-line entry point and compatibility facade
- `ui_server.py`: thin browser UI launcher
- `cea_hybrid/config.py`: JSON loading, sweep expansion, and validation
- `cea_hybrid/variables.py`: documented output-variable and plot-metric selection
- `cea_hybrid/calculations.py`: CEA case evaluation
- `cea_hybrid/nozzle_sizing.py`: minimal target-thrust nozzle sizing derived from CEA outputs
- `cea_hybrid/sweep.py`: multiprocessing sweep orchestration
- `cea_hybrid/outputs.py`: CSV and SVG export helpers
- `cea_hybrid/ui_backend.py`: UI payload shaping and request parsing
- `cea_hybrid/server.py`: HTTP server and background sweep job state
- `ui/`: HTML, CSS, and JavaScript for the interactive interface
- `inputs.json`: sweep definitions, output path, and model settings
- `test.py`: small direct CEA sanity check
- `outputs/`: generated CSV files after a run
- `outputs/plots/temperature_pairs/`: one dashboard per fuel/oxidizer temperature pair

## Requirements

- Python 3
- Installed `cea` package
- `numpy`

If you use the included virtual environment, activate it before running the script.

## Browser UI

Run the local UI server:

```powershell
python ui_server.py
```

Then open `http://127.0.0.1:8000` in a browser.

The UI includes:

- main input controls for target thrust, maximum nozzle exit diameter, target chamber pressure, and desired infill percentage
- advanced controls for `O/F`, fuel temperature, oxidizer temperature, `Ae/At` cap mode, and optional custom `Ae/At` start/end/step sweep
- interactive in-browser plots generated from raw sweep data
- zoom, pan, legend toggle, legend highlight, and chart expansion
- downloadable CSV files for all converged cases and the highest-Isp case in the selected fixed conditions

## Performance

- `cpu_workers` in `inputs.json` controls sweep parallelism
- Use `"auto"` to use all logical CPU threads
- Use `1` to force single-process execution for debugging
- GPU acceleration is not enabled: the current `cea` backend is CPU-bound and this project does not include CUDA or GPU kernels

## Script Workflow

1. Edit `inputs.json` to define the sweep ranges or explicit value lists.
2. Set `target_thrust_n`, `max_exit_diameter_cm`, `pc_bar`, and the sweep inputs you want to study.
3. Run the main script:

```powershell
python main.py
```

4. Review the generated CSV files in `outputs/`.
5. Open the SVG files in `outputs/plots/temperature_pairs/` for raw heatmap dashboards by temperature pair.

## Input Format

`inputs.json` supports either explicit lists or range objects for sweep values.

Example list:

```json
"abs_volume_fractions": [0.05, 0.1, 0.15, 0.2]
```

Example range:

```json
"of": { "start": 2.0, "stop": 12.0, "count": 81 }
```

Supported sweep keys:

- `ae_at`
- `of`
- `abs_volume_fractions`
- `fuel_temperatures_k`
- `oxidizer_temperatures_k`

By default, `sweeps.ae_at` starts at 1, uses step 1, and derives the candidate upper bound from `max_exit_diameter_cm` plus `target_thrust_n`. The generated candidate range starts just above 1 internally because the CEA supersonic area-ratio solver requires `Ae/At > 1`.

Advanced `Ae/At` controls:

- Set `ae_at_cap_mode` to `"exit_diameter"` to filter cases whose post-CEA circular-equivalent exit diameter exceeds `max_exit_diameter_cm`
- Set `ae_at_cap_mode` to `"area_ratio"` to cap the sweep directly at `max_area_ratio`
- Set `sweeps.ae_at.custom_enabled` to `true` to use explicit `start`, `stop`, and `step` values

Plot settings:

- `plots.enabled`: turn graph generation on or off
- `plots.metric`: choose which result field is visualized in the heatmaps and raw UI chart
- `plots.output_dir`: folder inside `outputs/` where the SVG files are written

## Output Files

After each run, the script writes:

- `outputs/all_cases.csv`: every converged sweep point
- `outputs/failures.csv`: failed or unconverged cases
- `outputs/cases_abs_*.csv`: all converged cases split by ABS volume fraction
- `outputs/plots/temperature_pairs/dashboard_*.svg`: one raw heatmap dashboard per fuel/oxidizer temperature pair

## Notes

- The ABS chemistry is modeled with a simplified styrene/butadiene surrogate.
- Density values and mixture shares are first-pass engineering assumptions.
- Throat area uses the CEA characteristic-velocity relation `At = mdot * c* / Pc`, so the reported design throat Mach is exactly 1.0.
- Results depend on the species definitions available in the installed CEA database.
