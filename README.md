# CEA Hybrid Script

This project runs NASA CEA-based performance calculations for a hybrid rocket concept using nitrous oxide oxidizer, a paraffin surrogate fuel, and an ABS surrogate blend. The project includes both a sweep script and a local browser UI for running parameter studies, inspecting plots, and comparing optimized designs.

## What It Does

- Evaluates hybrid rocket performance with the `cea` Python package
- Sweeps across user-defined `O/F` and `Ae/At` values, with configurable reactant temperature and infill target
- Writes full raw-case CSV data plus summary CSV files for best cases
- Generates organized SVG overview plots and temperature-pair dashboards automatically
- Reports key outputs such as `Isp`, `Cf`, mass flow, chamber temperature, and nozzle dimensions

## Project Files

- `main.py`: main analysis script
- `ui_server.py`: local browser UI server
- `ui/`: HTML, CSS, and JavaScript for the interactive interface
- `inputs.json`: sweep definitions, output path, and model settings
- `test.py`: small direct CEA sanity check
- `outputs/`: generated CSV files after a run
- `outputs/plots/overview/`: high-level summary plots
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

- input controls for thrust, chamber pressure, `Ae/At`, `O/F`, fixed reactant temperature, and desired infill percentage
- hybrid sizing inputs for `D_p`, burn time, target `L*`, and either a literature regression model or manual `a,n` override
- interactive in-browser plots generated from raw sweep data
- zoom, pan, legend toggle, legend highlight, and chart expansion
- optimized design cards, hybrid layout diagrams, and compact engineering tables for the selected fixed conditions

Hybrid sizing notes:

- `D_p` is the initial circular fuel-port diameter
- `G_ox`, volumetric loading, chamber diameter, and total fuel mass are derived from the sweep result plus `D_p` and burn time
- pre-chamber length uses an empirical axial showerhead estimate
- post-chamber length is solved from the requested characteristic length `L*`; if the grain plus pre-chamber already exceed that target, the solved post-chamber length is zero

## Performance

- `cpu_workers` in `inputs.json` controls sweep parallelism
- Use `"auto"` to use all logical CPU threads
- Use `1` to force single-process execution for debugging
- GPU acceleration is not enabled: the current `cea` backend is CPU-bound and this project does not include CUDA or GPU kernels

## Script Workflow

1. Edit `inputs.json` to define the sweep ranges or explicit value lists.
2. Set `target_thrust_n`, `pc_bar`, and the sweep inputs you want to study.
3. Run the main script:

```powershell
python main.py
```

4. Review the generated CSV files in `outputs/`.
5. Open the SVG files in `outputs/plots/overview/` for overall trends.
6. Open the SVG files in `outputs/plots/temperature_pairs/` for combined dashboards by temperature pair.

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

Plot settings:

- `plots.enabled`: turn graph generation on or off
- `plots.metric`: choose which result field is visualized in the heatmaps and best-case metric plots
- `plots.output_dir`: folder inside `outputs/` where the SVG files are written

## Output Files

After each run, the script writes:

- `outputs/all_cases.csv`: every converged sweep point
- `outputs/failures.csv`: failed or unconverged cases
- `outputs/best_by_ae_at.csv`: best case per `ABS fraction + temperature pair + Ae/At`
- `outputs/best_overall.csv`: best case per `ABS fraction + temperature pair`
- `outputs/cases_abs_*.csv`: all converged cases split by ABS volume fraction
- `outputs/plots/overview/best_*_vs_abs.svg`: summary best-case trends versus ABS fraction
- `outputs/plots/temperature_pairs/dashboard_*.svg`: one combined dashboard per fuel/oxidizer temperature pair

## Notes

- The ABS chemistry is modeled with a simplified styrene/butadiene surrogate.
- Density values and mixture shares are first-pass engineering assumptions.
- Results depend on the species definitions available in the installed CEA database.
