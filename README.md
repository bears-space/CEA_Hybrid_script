# Hybrid Rocket Workflow

This project now has two layers plus a higher-fidelity internal-ballistics extension:

- `cea_hybrid/` and `blowdown_hybrid/`: the existing working physics and UI/backend codepaths
- `src/`: the new modular workflow layer for standalone CEA runs, nominal 0D runs, Step 1 sensitivity/corner studies, Step 2 geometry freeze, and Step 3 quasi-1D internal ballistics

The refactor keeps the legacy CEA and blowdown logic in place for compatibility, but routes new analysis workflows through explicit interfaces instead of UI-coupled script calls.

## Current Scope

Implemented now:

- separated CEA module callable from Python
- reusable `run_0d_case()` workflow facade around the current 0D hybrid blowdown model
- unified thrust / `Isp` / `Cf` / `c*` bookkeeping across CEA seed, first-pass sizing, and transient results
- lightweight cached CEA lookup for transient `c*(O/F)` and nozzle performance variation
- nominal metric extraction
- constraint evaluation
- one-at-a-time sensitivity analysis
- named corner-case analysis
- Step 2 first-pass geometry freeze
- Step 3 quasi-1D internal ballistics using the frozen Step 2 geometry
- 0D vs 1D comparison exports
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
  - `solver_1d.py`: reusable `run_1d_ballistics_case(config, geometry, ...)` facade
  - `axial_mesh.py`: axial discretization helpers for the grain/port
  - `ballistics_1d.py`: local axial marching and fuel-addition logic
  - `performance_lookup.py`: lightweight cached CEA lookup for transient `c*` and nozzle performance
  - `case_runner.py`: nominal case orchestration
  - `state_1d.py`: typed quasi-1D settings and solver state
  - `stop_conditions.py`: stop/status normalization
- `src/analysis/`
  - `ballistics_comparison.py`: 0D vs 1D summary deltas
  - `metrics.py`: time-history reduction to design metrics
  - `constraints.py`: constraint checking
  - `geometry_checks.py`: hard geometry validity checks for first-pass grains
  - `pressure_budget.py`: explicit tank -> feed -> injector -> chamber bookkeeping helpers
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
  - `ballistics_export.py`: Step 3 time-history, axial-field, and comparison exports
  - `csv_export.py`: CSV writers
  - `geometry_export.py`: geometry JSON/CSV/text exports
  - `plotting.py`: lightweight SVG plot generation without matplotlib
  - `report_tables.py`: simple report-table helpers
- `src/models/regression.py`: reusable local power-law regression submodel
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
python main.py --mode ballistics_1d
```

Supported arguments:

```powershell
python main.py --mode cea --cea-config input/cea_config.json --output-dir output
python main.py --mode nominal --config input/design_config.json --output-dir output
python main.py --mode oat --config input/design_config.json --output-dir output
python main.py --mode corners --config input/design_config.json --output-dir output
python main.py --mode freeze_geometry --config input/design_config.json --cea-config input/cea_config.json --output-dir output
python main.py --mode ballistics_1d --config input/design_config.json --cea-config input/cea_config.json --output-dir output
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
- `--mode ballistics_1d`
  - consumes the frozen Step 2 baseline geometry
  - runs the new quasi-1D internal ballistics solver
  - can compare the 1D result against the reusable 0D nominal case
  - writes outputs under `output/ballistics_1d/`

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
- `isp_sl_s`
- `isp_vac_s`
- `cf`
- `cf_sea_level`
- `cf_vac`
- `gamma_e`
- `molecular_weight_exit`
- `chamber_temperature_k`
- `exit_pressure_bar`
- `exit_temperature_k`
- staged sea-level / vacuum thrust values
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
- uses a lightweight cached CEA lookup so transient `c*` varies with `O/F`
- uses one explicit pressure chain: `p_tank -> dp_feed -> p_injector_inlet -> dp_injector -> p_chamber`
- standardizes time histories and stop/status handling

Returned histories include:

- `t_s`
- `tank_pressure_bar`
- `tank_temperature_k`
- `tank_quality`
- `oxidizer_mass_remaining_kg`
- `mdot_ox_kg_s`
- `mdot_f_kg_s`
- `mdot_total_kg_s`
- `of_ratio`
- `pc_bar`
- `thrust_transient_actual_n`
- `thrust_vac_n`
- `isp_transient_s`
- `cstar_effective_mps`
- `cf_actual`
- `dp_feed_over_pc`
- `dp_injector_over_pc`
- `dp_total_over_ptank`
- `port_radius_mm`
- `grain_web_remaining_mm`

## Step 3 1D / Quasi-1D Ballistics

Public Step 3 entry point:

- `src/simulation/solver_1d.py`
- `run_1d_ballistics_case(config, geometry, cea_data=None, optional_seed_state=None) -> dict`

The 1D model:

- consumes the Step 2 `GeometryDefinition`
- reuses the current blowdown/feed/injector runtime inputs instead of replacing them
- discretizes the active grain length axially
- applies the baseline regression law locally as `rdot = a * Gox^n`
- adds fuel cell-by-cell and grows the port radius cell-by-cell
- keeps chamber/nozzle closure reduced-order through the same `c*` / `Cf` bookkeeping used elsewhere
- exports both time histories and axial distributions
- records a terminal axial snapshot at the actual end-of-run geometry, so the final axial profile and final port-size metrics reflect the last applied port-growth update

Current explicit quasi-1D approximation:

- oxidizer mass flow is conserved along the port in the current Step 3 model
- fuel is added locally from regression, so total mass flow increases downstream and local `O/F` decreases downstream
- a configurable axial correction profile is available for the axial showerhead baseline so the port can evolve non-uniformly without detailed injector CFD

This is intentional. It gives a useful and fast resolved internal-ballistics layer while keeping the interfaces open for later CFD-informed or test-calibrated submodels.

## Step 1 Design Config

`defaults.json` contains the full organized project defaults.

`input/design_config.json` is now an optional override file layered on top of the `design_workflow` section from `defaults.json`.

The design-workflow section is organized as:

- `nominal`
  - `performance`
  - `blowdown`
  - `loss_factors`
- `performance_lookup`
- `ballistics_1d`
- `uncertainty`
- `constraints`
- `geometry_policy`
- `sensitivity_metrics`
- `corner_cases`

`performance_lookup` controls the lightweight transient CEA interpolation layer, including:

- whether the lookup is enabled
- O/F padding around the nominal point
- number of sampled CEA points
- whether the solver falls back to the seed-point performance if lookup generation fails

`geometry_policy` contains the explicit Step 2 freeze heuristics, including:

- single-port baseline flag
- prechamber/postchamber enable flags
- grain-to-chamber radial clearance
- injector-face margin factor
- prechamber/postchamber length fractions
- placeholder injector plate and chamber wall thicknesses
- soft L* warning band
- minimum burnout web
- maximum port-to-outer-radius ratio
- maximum grain slenderness ratio
- geometry checks tied back to Step 1 nominal and corner-case constraint status

`ballistics_1d` contains the Step 3 quasi-1D settings, including:

- axial cell count
- quasi-1D time step and maximum simulation time
- ambient pressure
- geometry input source
- optional geometry auto-freeze behavior
- performance lookup mode
- regression model mode
- prechamber/postchamber handling mode
- station count for axial plots
- axial correction mode for the showerhead baseline
- maximum allowed fractional web growth per time step for solver-stability guarding

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

Those nominal outputs now distinguish:

- seed values
- derived first-pass estimates
- simulated initial values
- simulated final values
- constraint results

The pressure budget is explicit in both the transient histories and the UI/report output:

- tank pressure
- feed pressure drop
- injector inlet pressure
- injector pressure drop
- chamber pressure
- feed / injector / total pressure-drop ratios

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

Ballistics 1D mode writes:

- `ballistics_1d_history.csv`
- `ballistics_1d_axial_history.csv`
- `ballistics_1d_final_axial_profile.csv`
- `ballistics_1d_metrics.csv`
- `ballistics_1d_metrics.json`
- `ballistics_1d_constraints.csv`
- `ballistics_1d_constraints.json`
- `ballistics_1d_result.json`
- `ballistics_1d_summary.txt`
- `pc_vs_time.svg`
- `thrust_vs_time.svg`
- `of_vs_time.svg`
- `mass_flow_vs_time.svg`
- `port_radius_stations_vs_time.svg`
- `gox_stations_vs_time.svg`
- `final_port_radius_vs_x.svg`
- `final_regression_rate_vs_x.svg`
- `ballistics_1d_vs_0d.csv` and `ballistics_1d_vs_0d.json` when 0D comparison is enabled
- `compare_pc_0d_vs_1d.svg`
- `compare_thrust_0d_vs_1d.svg`
- `compare_of_0d_vs_1d.svg`

The axial CSV exports include:

- local port radius and area
- wetted perimeter
- conserved oxidizer mass flow and local oxidizer flux
- local regression rate
- local fuel addition rate
- downstream cumulative fuel flow and total mass flow
- local `O/F`

CEA mode writes:

- legacy sweep CSVs and SVGs under `output/cea/`
- `cea_config_used.json`
- `highest_isp_case.json`

## Automated Checks

Current test coverage includes:

- legacy first-pass sizing tests in `tests/test_blowdown_first_pass.py`
- new Step 1 workflow smoke tests in `tests/test_step1_workflow.py`
- Step 2 geometry-freeze smoke tests in `tests/test_geometry_freeze.py`
- Step 3 quasi-1D smoke tests in `tests/test_ballistics_1d.py`

Run:

```powershell
python -m unittest tests.test_blowdown_first_pass tests.test_step1_workflow tests.test_geometry_freeze tests.test_ballistics_1d
```

## Notes And TODOs

Current placeholders or intentionally simplified areas:

- the Step 1 nominal config uses an explicit seed performance point instead of automatically pulling from a CEA case
- the separated CEA module already supports extracting a highest-Isp point, but there is not yet a fully declarative config path that wires a selected CEA result into the Step 1 nominal JSON automatically
- plots are written as lightweight SVGs because `matplotlib` is not installed in the current environment
- the current 0D solver still uses the existing rigid, adiabatic, saturated two-phase nitrous assumptions
- transient performance now varies through a lightweight cached CEA lookup, but it is still not a full finite-rate combustion or detailed nozzle-flow model
- the Step 2 geometry freeze is intentionally analytical: injector face, wall thickness, prechamber, and postchamber dimensions are configurable placeholders, not final CAD or FEA-backed dimensions
- the current Step 3 solver is quasi-1D, not CFD: it does not resolve detailed injector-hole flow distribution, finite-rate chemistry, or chamber recirculation
- later refinement should plug CFD-informed injector distribution, improved oxidizer-consumption bookkeeping, regression calibration, and test-derived correction factors into the existing Step 3 interfaces instead of replacing the workflow

Those are deliberate continuity choices, not silent physics changes.
