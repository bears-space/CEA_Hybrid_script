# Hybrid Rocket Workflow

This project now has two layers:

- `cea_hybrid/` and `blowdown_hybrid/`: the existing working physics and UI/backend codepaths
- `src/`: the new modular workflow layer for standalone CEA runs, nominal 0D runs, Step 1 sensitivity/corner studies, and Step 2 geometry freeze

The refactor keeps the legacy CEA and blowdown logic in place for compatibility, but routes new analysis workflows through explicit interfaces instead of UI-coupled script calls.

## Current Scope

Implemented now:

- separated CEA module callable from Python
- reusable `run_0d_case()` workflow facade around the current 0D hybrid blowdown model
- nominal metric extraction
- constraint evaluation
- one-at-a-time sensitivity analysis
- named corner-case analysis
- Step 2 first-pass geometry freeze
- CSV/JSON/SVG exports
- argparse-based `main.py` entry point

Not implemented yet:

- CFD
- detailed injector geometry beyond the equivalent-orifice model
- structural FEA
- thermal FEA

## Project Structure

Top-level:

- `main.py`: workflow CLI
- `defaults.json`: single source of truth for all project default values for CEA and the blowdown/design workflow
- `constants.json`: single source of truth for project constants and option metadata
- `input/design_config.json`: optional design-workflow override file
- `input/cea_config.json`: optional CEA override file
- `src/`: new modular workflow package
- `cea_hybrid/`: legacy CEA sweep implementation kept intact
- `blowdown_hybrid/`: legacy 0D blowdown implementation kept intact
- `ui/`, `ui_server.py`, `blowdown_ui.py`: existing browser UI path

New workflow package:

- `src/cea/`
  - `cea_runner.py`: callable wrappers around the legacy CEA solver path
  - `cea_parser.py`: dict-to-dataclass parsing
  - `cea_interface.py`: public CEA API
  - `cea_types.py`: typed CEA result objects
- `src/simulation/`
  - `solver_0d.py`: reusable `run_0d_case(config)` facade
  - `case_runner.py`: nominal case orchestration
  - `stop_conditions.py`: stop/status normalization
- `src/analysis/`
  - `metrics.py`: time-history reduction to design metrics
  - `constraints.py`: constraint checking
  - `sensitivity.py`: OAT sensitivity
  - `corner_cases.py`: named corner-case runs
  - `summaries.py`: CSV row shaping
- `src/sizing/`
  - `first_pass_sizing.py`: first-pass sizing helpers re-exported from the legacy blowdown path
  - `geometry_init.py`: geometric initialization helpers
  - `geometry_types.py`: frozen geometry dataclass
  - `geometry_rules.py`: deterministic geometry rules and sanity checks
  - `geometry_freeze.py`: Step 2 geometry-freeze orchestration
- `src/post/`
  - `csv_export.py`: CSV writers
  - `geometry_export.py`: geometry JSON/CSV/text exports
  - `plotting.py`: lightweight SVG plot generation without matplotlib
  - `report_tables.py`: simple report-table helpers
- `src/config_schema.py`: workflow defaults and config loading
- `src/io_utils.py`, `src/units.py`, `src/constants.py`: shared utilities

## Legacy Compatibility

Kept intentionally:

- `cea_hybrid/` remains the source of truth for the current CEA sweep behavior and CSV/SVG sweep exports
- `blowdown_hybrid/` remains the source of truth for the current first-pass sizing and 0D blowdown physics
- the browser UI path is untouched architecturally and still uses the legacy backend modules

New data-source boundary:

- hardcoded Python defaults were replaced with root-level `defaults.json`
- hardcoded Python project constants were replaced with root-level `constants.json`
- `input/*.json` are now optional override files instead of duplicate default snapshots

One performance-focused internal change was made to the legacy blowdown layer:

- `blowdown_hybrid/thermo.py` now caches saturated N2O property lookups by temperature

That change preserves the existing equations and assumptions, but makes repeated nominal/OAT/corner runs practical.

## Installation

Requirements already used by the current project:

- Python 3
- `cea`
- `numpy`
- `CoolProp`

The included virtual environment already contains the required packages on this machine.

## CLI Usage

Run the new workflow CLI:

```powershell
python main.py --mode cea
python main.py --mode nominal
python main.py --mode oat
python main.py --mode corners
python main.py --mode freeze_geometry
```

Supported arguments:

```powershell
python main.py --mode cea --cea-config input/cea_config.json --output-dir output
python main.py --mode nominal --config input/design_config.json --output-dir output
python main.py --mode oat --config input/design_config.json --output-dir output
python main.py --mode corners --config input/design_config.json --output-dir output
python main.py --mode freeze_geometry --config input/design_config.json --cea-config input/cea_config.json --output-dir output
```

Modes:

- `--mode cea`
  - runs the separated CEA sweep module
  - if `--cea-config` is omitted, it uses the `cea` section from `defaults.json`
  - writes outputs under `output/cea/`
- `--mode nominal`
  - runs one nominal 0D case
  - if `--config` is omitted, it uses the `design_workflow` section from `defaults.json`
  - writes outputs under `output/nominal/`
- `--mode oat`
  - runs one-at-a-time sensitivity cases around the nominal design
  - writes outputs under `output/sensitivity/`
- `--mode corners`
  - runs configured named corner cases
  - writes outputs under `output/corners/`
- `--mode freeze_geometry`
  - runs the nominal case plus Step 1 OAT and corner summaries
  - requests a matching reference point from the separated CEA module
  - freezes one baseline engine geometry for later workflow stages
  - writes outputs under `output/geometry/`

## CEA Module

Public CEA entry points live in `src/cea/cea_interface.py`.

Key interfaces:

- `run_cea_case(cea_config) -> CEAPerformancePoint`
- `run_cea_study(raw_config) -> CEASweepResult`
- `get_cea_performance_point(result, selector="highest_isp")`
- `load_cea_config(path)`

Available downstream CEA fields include:

- `cstar_mps`
- `isp_s`
- `isp_vac_s`
- `cf`
- `gamma_e`
- `molecular_weight_exit`
- `chamber_temperature_k`
- `exit_pressure_bar`
- `exit_temperature_k`
- nozzle throat and exit areas

The CEA module does not select chamber pressure. It evaluates thermochemistry at the specified conditions.

## 0D Solver Interface

Public 0D entry point:

- `src/simulation/solver_0d.py`
- `run_0d_case(config: dict) -> dict`

The solver facade:

- builds a seed performance point
- maps the nominal study config into the current blowdown model inputs
- runs the existing coupled tank/feed/injector/grain/nozzle closure
- standardizes time histories and stop/status handling

Returned histories include:

- `t_s`
- `tank_pressure_bar`
- `tank_temperature_k`
- `tank_quality`
- `oxidizer_mass_remaining_kg`
- `mdot_ox_kg_s`
- `mdot_f_kg_s`
- `of_ratio`
- `pc_bar`
- `thrust_n`
- `port_radius_mm`
- `grain_web_remaining_mm`

## Step 1 Design Config

`defaults.json` contains the full organized project defaults.

`input/design_config.json` is now an optional override file layered on top of the `design_workflow` section from `defaults.json`.

The design-workflow section is organized as:

- `nominal`
  - `performance`
  - `blowdown`
  - `loss_factors`
- `uncertainty`
- `constraints`
- `geometry_policy`
- `sensitivity_metrics`
- `corner_cases`

`geometry_policy` contains the explicit Step 2 freeze heuristics, including:

- single-port baseline flag
- prechamber/postchamber enable flags
- grain-to-chamber radial clearance
- injector-face margin factor
- prechamber/postchamber length fractions
- placeholder injector plate and chamber wall thicknesses
- soft L* warning band
- geometry checks tied back to Step 1 nominal and corner-case constraint status

Currently supported uncertainty parameters:

- `tank_temperature_k`
- `fill_fraction`
- `usable_ox_fraction`
- `injector_cd`
- `regression_a`
- `regression_n`
- `cstar_efficiency`
- `cf_efficiency`
- `usable_fuel_fraction`
- `injector_dp_fraction`
- `line_loss_multiplier`
- `nozzle_discharge_factor`

Supported uncertainty modes:

- `percent`
- `absolute`

## Outputs

Nominal mode writes:

- `nominal_history.csv`
- `nominal_metrics.csv`
- `nominal_metrics.json`
- `nominal_constraints.csv`
- `nominal_constraints.json`
- `pc_vs_time.svg`
- `thrust_vs_time.svg`
- `mass_flow_vs_time.svg`
- `of_vs_time.svg`
- `port_radius_vs_time.svg`
- `tank_pressure_vs_time.svg`

OAT mode writes:

- `oat_cases.csv`
- `ranking_<metric>.csv`
- `ranking_<metric>.svg`
- `nominal_metrics.json`

Corner mode writes:

- `corner_case_summary.csv`
- `corner_case_summary.json`
- `pc_overlay.svg`
- `thrust_overlay.svg`
- `of_overlay.svg`

Geometry mode writes:

- `baseline_geometry.json`
- `baseline_geometry.csv`
- `geometry_summary.txt`
- `geometry_context.json`
- `cea_reference_case.json` when the reference CEA point converges

CEA mode writes:

- legacy sweep CSVs and SVGs under `output/cea/`
- `cea_config_used.json`
- `highest_isp_case.json`

## Automated Checks

Current test coverage includes:

- legacy first-pass sizing tests in `tests/test_blowdown_first_pass.py`
- new Step 1 workflow smoke tests in `tests/test_step1_workflow.py`
- Step 2 geometry-freeze smoke tests in `tests/test_geometry_freeze.py`

Run:

```powershell
python -m unittest tests.test_blowdown_first_pass tests.test_step1_workflow tests.test_geometry_freeze
```

## Notes And TODOs

Current placeholders or intentionally simplified areas:

- the Step 1 nominal config uses an explicit seed performance point instead of automatically pulling from a CEA case
- the separated CEA module already supports extracting a highest-Isp point, but there is not yet a fully declarative config path that wires a selected CEA result into the Step 1 nominal JSON automatically
- plots are written as lightweight SVGs because `matplotlib` is not installed in the current environment
- the current 0D solver still uses the existing rigid, adiabatic, saturated two-phase nitrous assumptions and constant `c*` / `Cf` closure
- the Step 2 geometry freeze is intentionally analytical: injector face, wall thickness, prechamber, and postchamber dimensions are configurable placeholders, not final CAD or FEA-backed dimensions
- future Step 3 work should consume `baseline_geometry.json` directly and refine internal ballistics or submodels without replacing the current 0D orchestration layer

Those are deliberate continuity choices, not silent physics changes.
