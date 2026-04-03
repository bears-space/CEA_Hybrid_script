# CEA Hybrid Script

This project runs NASA CEA-based performance calculations for a hybrid rocket concept using nitrous oxide oxidizer, a paraffin surrogate fuel, and an ABS surrogate blend. The script reads sweep settings from `inputs.json`, evaluates every parameter combination, writes CSV outputs, and generates organized SVG dashboards for quick visual comparison.

## What It Does

- Evaluates hybrid rocket performance with the `cea` Python package
- Sweeps across user-defined `O/F`, `Ae/At`, fuel temperature, oxidizer temperature, and ABS volume fraction values
- Writes full raw-case CSV data plus summary CSV files for best cases
- Generates organized SVG overview plots and temperature-pair dashboards automatically
- Reports key outputs such as `Isp`, `Cf`, mass flow, chamber temperature, and nozzle dimensions

## Project Files

- `main.py`: main analysis script
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

## How To Use

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
