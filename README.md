# BEARS Hybrid Engine Workflow

Python project for first-pass hybrid rocket engine design and simulation with an N2O oxidizer, paraffin fuel, ABS structural fraction, reduced-order feed and injector models, injector geometry synthesis, hydraulic validation against cold-flow data, first-pass structural and thermal sizing, reduced-order nozzle off-design and environment assessment, and CFD campaign planning plus correction-package reuse.

## Architecture

The project is organized by domain rather than by workflow stage.

- `src/cea/`: thermochemistry and CEA integration.
- `src/simulation/`: 0D engine runtime, quasi-1D internal ballistics, state models, and solver utilities.
- `src/sizing/`: first-pass sizing and baseline geometry freeze logic.
- `src/injector_design/`: axial showerhead injector synthesis, back-calculation, checks, and export.
- `src/hydraulic_validation/`: dataset ingest, prediction, calibration, residual analysis, and calibration-package reuse.
- `src/structural/`: first-pass structural load cases, chamber and closure sizing, injector plate checks, retention placeholders, mass estimates, and export.
- `src/thermal/`: first-pass thermal load cases, region-wise heat-transfer estimates, wall-temperature checks, protection placeholders, and export.
- `src/nozzle_offdesign/`: ambient-case generation, transient nozzle off-design evaluation, expansion-state checks, separation-risk heuristics, recommendations, and export.
- `src/cfd/`: ordered CFD target generation, case packaging, result ingest, correction bridges, and export.
- `src/testing/`: staged test campaign planning, article definitions, instrumentation plans, data ingest, model-vs-test comparison, hot-fire calibration packages, and readiness gates.
- `src/analysis/`: sensitivity, corner cases, pressure-budget comparisons, and summary helpers.
- `src/post/`: CSV, JSON, text, and plot export helpers.
- `src/artifacts/`: consolidated run-root output management.
- `src/config/`: canonical configuration package for normalized workflow settings.
- `src/workflows/`: shared workflow runner for the CLI and browser UI.
- `src/ui/`: workflow dashboard HTTP server.

`main.py` is intentionally minimal and delegates to `src.cli` and `src.workflows.engine`.

## Workflow Modes

CLI modes:

- `cea`
- `nominal`
- `oat`
- `corners`
- `geometry`
- `internal_ballistics`
- `injector_design`
- `hydraulic_predict`
- `hydraulic_calibrate`
- `hydraulic_compare`
- `structural_size`
- `thermal_size`
- `nozzle_offdesign`
- `cfd_plan`
- `cfd_export_cases`
- `cfd_ingest_results`
- `cfd_apply_corrections`
- `test_plan`
- `test_define_articles`
- `test_ingest_data`
- `test_compare_model`
- `test_calibrate_hotfire`
- `test_readiness`

Examples:

```bash
python main.py --mode nominal
python main.py --mode geometry --config input/design_config.json --cea-config input/cea_config.json
python main.py --mode injector_design --config input/design_config.json --cea-config input/cea_config.json
python main.py --mode hydraulic_calibrate --config input/design_config.json --hydraulic-config input/hydraulic_validation_config.json
python main.py --mode structural_size --config input/design_config.json --structural-config input/structural_config.json
python main.py --mode thermal_size --config input/design_config.json --structural-config input/structural_config.json --thermal-config input/thermal_config.json
python main.py --mode nozzle_offdesign --config input/design_config.json --structural-config input/structural_config.json --thermal-config input/thermal_config.json --nozzle-offdesign-config input/nozzle_offdesign_config.json
python main.py --mode cfd_plan --config input/design_config.json --structural-config input/structural_config.json --thermal-config input/thermal_config.json --nozzle-offdesign-config input/nozzle_offdesign_config.json --cfd-config input/cfd_config.json
python main.py --mode cfd_apply_corrections --config input/design_config.json --structural-config input/structural_config.json --thermal-config input/thermal_config.json --nozzle-offdesign-config input/nozzle_offdesign_config.json --cfd-config input/cfd_config.json
python main.py --mode test_plan --config input/design_config.json --structural-config input/structural_config.json --thermal-config input/thermal_config.json --nozzle-offdesign-config input/nozzle_offdesign_config.json --cfd-config input/cfd_config.json --testing-config input/test_campaign_config.json
python main.py --mode test_calibrate_hotfire --config input/design_config.json --structural-config input/structural_config.json --thermal-config input/thermal_config.json --nozzle-offdesign-config input/nozzle_offdesign_config.json --testing-config input/test_campaign_config.json
python main.py --mode test_readiness --config input/design_config.json --structural-config input/structural_config.json --thermal-config input/thermal_config.json --nozzle-offdesign-config input/nozzle_offdesign_config.json --testing-config input/test_campaign_config.json
```

Legacy mode aliases are still accepted for compatibility, but the canonical names above are the supported interface going forward.

## Config Files

Primary input files:

- `input/design_config.json`
- `input/cea_config.json`
- `input/hydraulic_validation_config.json`
- `input/structural_config.json`
- `input/thermal_config.json`
- `input/nozzle_offdesign_config.json`
- `input/cfd_config.json`
- `input/test_campaign_config.json`

Canonical top-level design-config sections:

- `nominal`
- `performance_lookup`
- `geometry_policy`
- `internal_ballistics`
- `injector_design`
- `hydraulic_validation`
- `structural`
- `thermal`
- `nozzle_offdesign`
- `cfd`
- `testing`
- `uncertainty`
- `corner_cases`
- `constraints`

The config loader still accepts earlier compatibility aliases where needed, but normalized runtime configs use the canonical section names above.

## Outputs

All workflow artifacts are consolidated under a run root:

```text
output/
  latest_run.json
  runs/
    <run_id>/
      manifest.json
      thermochemistry/
      performance/
      analysis/
      geometry/
      internal_ballistics/
      injector_design/
      hydraulic_validation/
      structural/
      thermal/
      nozzle_offdesign/
      cfd/
      testing/
```

Each run writes a `manifest.json` with the mode, summary metadata, and generated section paths.

Representative artifact names:

- `geometry/geometry_definition.json`
- `internal_ballistics/internal_ballistics_metrics.json`
- `injector_design/injector_geometry.json`
- `hydraulic_validation/hydraulic_predictions.csv`
- `hydraulic_validation/calibration_package.json`
- `structural/structural_sizing.json`
- `structural/structural_load_cases.json`
- `thermal/thermal_sizing.json`
- `thermal/thermal_load_cases.json`
- `nozzle_offdesign/nozzle_offdesign_results.json`
- `nozzle_offdesign/nozzle_environment_cases.json`
- `cfd/cfd_campaign_plan.json`
- `cfd/cfd_case_definitions.json`
- `testing/test_campaign_plan.json`
- `testing/model_vs_test_comparisons.csv`
- `testing/hotfire_calibration_packages.json`
- `testing/readiness_summary.json`

## UI

Start the browser dashboard with either:

```bash
python ui_server.py
python blowdown_ui.py
```

The UI now uses the same shared workflow runner as the CLI. It exposes:

- thermochemistry
- nominal performance
- sensitivity
- corner cases
- geometry
- internal ballistics
- injector design
- hydraulic prediction and calibration
- structural sizing
- thermal sizing
- nozzle off-design and environment assessment
- CFD campaign planning and correction application
- test campaign planning, data ingest, hot-fire calibration, and readiness gating

The dashboard runs workflows in the background, shows run summaries, loads its workflow-mode catalog from the backend, and reads the latest run manifest plus artifact index from the consolidated output tree.

Frontend implementation notes:

- `ui/index.html`, `ui/howto.html`, and `ui/simulation.html` are now Vue 3 pages.
- `ui/vendor/vue.global.prod.js` vendors the Vue runtime locally so the dashboard does not depend on an external CDN at runtime.
- `ui/shared.js` holds browser-side helpers shared across the Vue apps.

UI usage notes:

- The editors are preloaded with effective defaults from the project defaults plus any `input/*.json` overrides that exist.
- You do not need to provide separate config files to run from the UI unless you want to replace or override those defaults.
- `Run Selected Workflow` executes the currently selected mode, not the entire catalog.
- Later-stage modes may still generate prerequisite artifacts inside the same run root when the selected workflow depends on them.

## Hydraulic Validation

`src/hydraulic_validation/` adds a calibration layer on top of the existing reduced-order feed and injector models. It supports:

- CSV and JSON dataset ingest
- injector-only, feed-only, and joint calibration
- surrogate-fluid labeling
- reusable calibration packages
- residual metrics and validation flags
- back-integration into the existing 0D and quasi-1D solvers

This layer is intentionally reduced-order. It does not add CFD, hot-fire calibration, or flashing two-phase injector flow modeling.

## Structural Sizing

`src/structural/` adds a first-pass structural sizing layer on top of the frozen geometry and reduced-order engine loads. It supports:

- explicit structural load cases from nominal 0D, corner-case envelopes, peak quasi-1D results, or user overrides
- chamber-shell pressure-vessel sizing with a thick-wall fallback warning path
- forward and aft closure sizing with simple circular-plate models
- injector-plate structural checks tied to the synthesized showerhead geometry when available
- fastener and nozzle-retention placeholders
- grain-support warnings based on web thickness, clearance, and slenderness
- structural mass breakdowns, validity flags, and exported summary artifacts

This layer is intentionally first-pass and auditable. It does not add FEA, thermal-structural coupling, weld design, fatigue, or certification logic.

## Thermal Sizing

`src/thermal/` adds a first-pass thermal sizing layer on top of the frozen geometry, reduced-order solver histories, injector geometry, and structural thickness selections. It supports:

- explicit transient thermal load cases from nominal 0D, corner-case envelopes, transient quasi-1D results, or user overrides
- Bartz-like region-wise gas-side heat-transfer placeholders for chamber, throat, nozzle, and injector-face checks
- two-node reduced-order wall-temperature histories with explicit lumped-model warnings
- chamber, prechamber, postchamber, throat, diverging-nozzle, and injector-face thermal validity checks
- optional liner and throat-insert placeholder sizing with first-pass protection mass estimates
- exported thermal summaries, transient histories, plots, and validity flags for reuse by later refinement work

This layer is intentionally first-pass and auditable. It does not add CFD, detailed conjugate heat transfer, ablation recession, regenerative cooling, film cooling, or hot-fire-calibrated heat-flux models.

## Nozzle Off-Design

`src/nozzle_offdesign/` adds a first-pass nozzle off-design and environment-check layer on top of the frozen geometry, solver histories, and structural/thermal outputs. It supports:

- explicit sea-level, altitude-point, vacuum, sweep, and ascent-profile placeholder environment cases
- transient evaluation across the actual burn using nominal 0D, transient quasi-1D, corner-envelope, or user-override source histories
- reduced-order thrust, `Cf`, `Isp`, and exit-pressure comparisons across ambient conditions
- explicit expansion-state classification and pressure-ratio separation-risk heuristics
- practical recommendations for ground-test versus flight use, including a separate ground-test nozzle recommendation path
- exported off-design summaries, transient histories, plots, and validity flags for reuse by later refinement work

This layer is intentionally first-pass and auditable. It does not add CFD, detailed separated-flow simulation, side-load prediction, trajectory optimization, or hot-fire-calibrated nozzle loss models.

## CFD Planning

`src/cfd/` adds a first-pass CFD target-definition and correction-bridge layer on top of the frozen geometry, injector geometry, solver histories, structural sizing, thermal sizing, and nozzle off-design results. It supports:

- explicit ordered CFD campaign generation with the default recommendation: injector first, then head-end, then nozzle, then broader reacting internal flow
- reduced-order operating-point selection from nominal 0D, quasi-1D, corner-case, thermal, and nozzle off-design outputs instead of arbitrary guessed points
- structured geometry-scope and boundary-condition packages for external CFD setup
- JSON and CSV ingest of summarized external CFD result files without depending on raw field data
- reusable correction packages for injector CdA, head-end distribution, thermal multipliers, and nozzle penalties
- optional correction application into reduced-order config overrides so the existing fast workflow can consume CFD-informed updates without a rewrite

This layer is intentionally supportive rather than primary. It does not add a CFD solver, mesh generation automation, raw field post-processing dependence, or a CFD-first replacement workflow.

## Testing

`src/testing/` adds a structured test-progression and model-feedback layer on top of the frozen geometry, injector geometry, hydraulic validation, structural sizing, thermal sizing, nozzle off-design results, and optional CFD context. It supports:

- explicit ordered campaign stages from coupon checks through cold flow, subscale hot-fire, full-scale short duration, and full-scale nominal duration
- traceable article definitions, instrumentation recommendations, and a lightweight test matrix
- JSON and CSV ingest of cleaned cold-flow or hot-fire datasets without turning the project into a DAQ or control system
- reduced-order model-vs-test comparison against the existing 0D and quasi-1D solver histories
- reusable hot-fire calibration packages for regression, efficiency, nozzle-loss, and thermal-multiplier updates
- explicit readiness gates and blocker reporting for stage-to-stage progression

This layer is intentionally supportive rather than primary. It does not add test-stand control, operations documentation, qualification logic, or empirical-only replacement of the reduced-order workflow.

Current regression suite:

```bash
python -m unittest \
  tests.test_blowdown_first_pass \
  tests.test_design_workflow \
  tests.test_geometry_baseline \
  tests.test_internal_ballistics \
  tests.test_injector_design \
  tests.test_hydraulic_validation \
  tests.test_structural_sizing \
  tests.test_thermal_sizing \
  tests.test_nozzle_offdesign \
  tests.test_cfd_workflow \
  tests.test_testing_workflow
```

## Notes

- The separate CEA path is preserved.
- The fast 0D and quasi-1D solvers are preserved.
- Injector geometry and hydraulic calibration are additive layers on top of the existing reduced-order engine workflow.
- Structural sizing is another additive reduced-order layer on top of the existing geometry, hydraulic, and performance workflow.
- Thermal sizing is another additive reduced-order layer on top of the existing geometry, injector, hydraulic, structural, and performance workflow.
- Nozzle off-design is another additive reduced-order layer on top of the existing geometry, performance, structural, and thermal workflow.
- CFD planning is another additive integration layer on top of the existing geometry, injector, hydraulic, structural, thermal, and nozzle workflow outputs.
- Structured test progression is another additive feedback and calibration layer on top of the existing geometry, injector, hydraulic, structural, thermal, nozzle, and CFD workflow outputs.
- Compatibility aliases remain in a few config and workflow entrypoints to reduce breakage during the refactor.
- Future work should continue to plug hot-fire updates, CFD-informed corrections, richer hydraulic characterization, automated CAD/mesh export, detailed nozzle-flow refinements, later FEA or thermal refinements, and richer test-stand metadata integration into the current reduced-order interfaces rather than replacing them.
