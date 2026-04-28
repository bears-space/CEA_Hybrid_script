"""Workflow mode metadata, aliases, and presentation helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class WorkflowModeDefinition:
    key: str
    title: str
    description: str
    editors: tuple[str, ...]


WORKFLOW_MODE_DEFINITIONS: tuple[WorkflowModeDefinition, ...] = (
    WorkflowModeDefinition("cea", "Thermochemistry", "NASA CEA sweeps and highest-Isp selection. Uses the CEA config only.", ("cea",)),
    WorkflowModeDefinition("nominal", "Nominal Performance", "Runs the fast 0D engine model with the current design config.", ("design",)),
    WorkflowModeDefinition("oat", "Sensitivity", "One-at-a-time perturbation study using the nominal design config.", ("design",)),
    WorkflowModeDefinition("corners", "Corner Cases", "Named corner-case analysis with the shared design config.", ("design",)),
    WorkflowModeDefinition("geometry", "Geometry", "Freezes the baseline engine geometry and captures supporting context.", ("design", "cea")),
    WorkflowModeDefinition("internal_ballistics", "Internal Ballistics", "Runs the quasi-1D axial solver with automatic or file-backed geometry reuse.", ("design", "cea")),
    WorkflowModeDefinition("injector_design", "Injector Design", "Synthesizes the showerhead injector geometry and back-calculates the reduced-order model.", ("design", "cea")),
    WorkflowModeDefinition("hydraulic_predict", "Hydraulic Predict", "Compares measured rig data against the current reduced-order hydraulic model.", ("design", "hydraulic")),
    WorkflowModeDefinition("hydraulic_calibrate", "Hydraulic Calibrate", "Fits feed and injector corrections, then exports a reusable calibration package.", ("design", "hydraulic")),
    WorkflowModeDefinition("hydraulic_compare", "Hydraulic Compare", "Loads a saved calibration package and compares calibrated versus nominal predictions.", ("design", "hydraulic")),
    WorkflowModeDefinition("structural_size", "Structural Sizing", "Sizes the chamber shell, closures, injector plate, retention hardware, and structural mass from existing reduced-order loads.", ("design", "cea", "hydraulic", "structural")),
    WorkflowModeDefinition("thermal_size", "Thermal Sizing", "Checks first-pass chamber, throat, nozzle, and injector-face thermal survivability from the existing reduced-order histories and structural selections.", ("design", "cea", "hydraulic", "structural", "thermal")),
    WorkflowModeDefinition("nozzle_offdesign", "Nozzle Off-Design", "Checks ambient sensitivity, expansion state, separation risk, and ground-test versus flight suitability for the current nozzle.", ("design", "cea", "hydraulic", "structural", "thermal", "nozzleOffdesign")),
    WorkflowModeDefinition("cfd_plan", "CFD Plan", "Builds the ordered CFD campaign, target definitions, operating points, and reusable correction templates.", ("design", "cea", "hydraulic", "structural", "thermal", "nozzleOffdesign", "cfd")),
    WorkflowModeDefinition("cfd_export_cases", "CFD Export Cases", "Exports structured CFD case definitions, geometry scopes, and boundary-condition packages for external setup.", ("design", "cea", "hydraulic", "structural", "thermal", "nozzleOffdesign", "cfd")),
    WorkflowModeDefinition("cfd_ingest_results", "CFD Ingest Results", "Loads summarized external CFD results, converts them into correction packages, and reports reduced-order impact targets.", ("design", "cea", "hydraulic", "structural", "thermal", "nozzleOffdesign", "cfd")),
    WorkflowModeDefinition("cfd_apply_corrections", "CFD Apply Corrections", "Applies ingested CFD correction packages to reduced-order config overrides without replacing the core workflow.", ("design", "cea", "hydraulic", "structural", "thermal", "nozzleOffdesign", "cfd")),
    WorkflowModeDefinition("test_plan", "Test Plan", "Builds the ordered coupon-to-full-scale campaign, test articles, instrumentation plans, and initial matrix.", ("design", "cea", "hydraulic", "structural", "thermal", "nozzleOffdesign", "cfd", "testing")),
    WorkflowModeDefinition("test_define_articles", "Test Articles", "Generates explicit coupon, cold-flow, subscale, and full-scale article definitions with instrumentation expectations.", ("design", "cea", "hydraulic", "structural", "thermal", "nozzleOffdesign", "cfd", "testing")),
    WorkflowModeDefinition("test_ingest_data", "Test Ingest", "Loads structured cold-flow or hot-fire datasets, cleans them, and extracts run summaries for reuse.", ("design", "cea", "hydraulic", "structural", "thermal", "nozzleOffdesign", "cfd", "testing")),
    WorkflowModeDefinition("test_compare_model", "Model vs Test", "Compares ingested test traces against the current 0D or 1D reduced-order model history.", ("design", "cea", "hydraulic", "structural", "thermal", "nozzleOffdesign", "cfd", "testing")),
    WorkflowModeDefinition("test_calibrate_hotfire", "Hot-Fire Calibrate", "Builds reusable hot-fire calibration packages for regression, efficiency, and thermal multipliers.", ("design", "cea", "hydraulic", "structural", "thermal", "nozzleOffdesign", "cfd", "testing")),
    WorkflowModeDefinition("test_readiness", "Test Readiness", "Evaluates progression gates and reports whether the campaign is ready to advance to the next stage.", ("design", "cea", "hydraulic", "structural", "thermal", "nozzleOffdesign", "cfd", "testing")),
)

# Default-safe end-to-end sequence for the UI "Run All" action.
# It intentionally excludes modes that require external datasets or ingest files.
RUN_ALL_SEQUENCE: tuple[str, ...] = (
    "cea",
    "nominal",
    "oat",
    "corners",
    "geometry",
    "internal_ballistics",
    "injector_design",
    "structural_size",
    "thermal_size",
    "nozzle_offdesign",
    "cfd_plan",
    "cfd_export_cases",
    "test_plan",
    "test_readiness",
)

CANONICAL_MODES = frozenset(mode.key for mode in WORKFLOW_MODE_DEFINITIONS)
MODE_ALIASES = {
    "freeze_geometry": "geometry",
    "ballistics_1d": "internal_ballistics",
    "synthesize_injector": "injector_design",
    "coldflow_predict": "hydraulic_predict",
    "coldflow_calibrate": "hydraulic_calibrate",
    "coldflow_compare": "hydraulic_compare",
}


def resolve_mode_alias(mode: str) -> str:
    """Resolve compatibility aliases to canonical workflow modes."""

    resolved = MODE_ALIASES.get(str(mode).strip().lower(), str(mode).strip().lower())
    if resolved not in CANONICAL_MODES:
        supported = ", ".join(sorted(CANONICAL_MODES))
        raise ValueError(f"Unsupported mode '{mode}'. Supported modes: {supported}.")
    return resolved


def mode_definitions_payload() -> list[dict[str, Any]]:
    """Return serializable mode metadata for the UI."""

    payload: list[dict[str, Any]] = []
    for definition in WORKFLOW_MODE_DEFINITIONS:
        item = asdict(definition)
        item["editors"] = list(definition.editors)
        payload.append(item)
    return payload


def summary_lines(result: Mapping[str, Any]) -> list[str]:
    """Generate concise human-readable summary lines for a workflow result."""

    mode = str(result["mode"])
    run_root = result["run"].root
    payload = result["payload"]
    if mode == "cea":
        return [
            f"Thermochemistry sweep completed: {payload['case_count']} converged case(s), {payload['failure_count']} failure(s).",
            f"Highest-Isp case: {payload['best_isp_s']:.3f} s",
            f"Wrote outputs to {run_root}",
        ]
    if mode == "nominal":
        return [
            f"Nominal case status: {payload['metrics']['status']} ({payload['metrics']['stop_reason']})",
            f"Average thrust: {payload['metrics']['thrust_avg_n']:.2f} N",
            f"Impulse: {payload['metrics']['impulse_total_ns']:.2f} N s",
            f"Constraints pass: {payload['constraints']['all_pass']}",
            f"Wrote outputs to {run_root}",
        ]
    if mode == "oat":
        return [
            f"Sensitivity study completed for {len(payload['cases'])} case variants.",
            f"Wrote outputs to {run_root}",
        ]
    if mode == "corners":
        return [
            f"Corner-case study completed for {len(payload['corners'])} named corner cases.",
            f"Wrote outputs to {run_root}",
        ]
    if mode == "geometry":
        geometry = payload["geometry"]
        return [
            f"Baseline geometry valid: {geometry.geometry_valid}",
            f"Chamber ID: {geometry.chamber_id_m * 1000.0:.2f} mm",
            f"Grain length: {geometry.grain_length_m * 1000.0:.2f} mm",
            f"Initial L*: {geometry.lstar_initial_m:.3f} m",
            f"Wrote outputs to {run_root}",
        ]
    if mode == "injector_design":
        geometry = payload["payload"]["injector_geometry"]
        effective_model = payload["payload"]["effective_model"]
        return [
            f"Injector geometry valid: {geometry.injector_geometry_valid}",
            f"Hole count: {geometry.hole_count}",
            f"Hole diameter: {geometry.hole_diameter_m * 1000.0:.3f} mm",
            f"Estimated CdA: {effective_model.effective_cda_m2 * 1.0e6:.3f} mm^2",
            f"Wrote outputs to {run_root}",
        ]
    if mode == "hydraulic_predict":
        return [
            f"Hydraulic prediction dataset: {payload['dataset'].dataset_name} ({len(payload['dataset'].points)} point(s))",
            f"Mass-flow RMSE: {payload['baseline_stats']['mdot_error_percent']['rmse']}",
            f"Wrote outputs to {run_root}",
        ]
    if mode == "hydraulic_calibrate":
        package = payload["calibration_package"]
        return [
            f"Hydraulic calibration mode: {package.calibration_mode}",
            f"Calibration valid: {package.calibration_valid}",
            f"Recommended model source: {package.recommended_model_source}",
            f"Calibrated mass-flow RMSE: {payload['calibrated_stats']['mdot_error_percent']['rmse']}",
            f"Wrote outputs to {run_root}",
        ]
    if mode == "hydraulic_compare":
        package = payload["calibration_package"]
        return [
            f"Hydraulic comparison against package mode: {package.calibration_mode}",
            f"Baseline mass-flow RMSE: {payload['baseline_stats']['mdot_error_percent']['rmse']}",
            f"Calibrated mass-flow RMSE: {payload['calibrated_stats']['mdot_error_percent']['rmse']}",
            f"Wrote outputs to {run_root}",
        ]
    if mode == "structural_size":
        structural_result = payload["payload"]["result"]
        return [
            f"Structural valid: {structural_result.structural_valid}",
            f"Governing load case: {structural_result.governing_load_case.case_name} ({structural_result.governing_load_case.source_stage})",
            f"Chamber wall thickness: {structural_result.chamber_wall_result.selected_thickness_m * 1000.0:.3f} mm",
            f"Estimated structural mass: {structural_result.total_structural_mass_estimate_kg:.3f} kg",
            f"Wrote outputs to {run_root}",
        ]
    if mode == "thermal_size":
        thermal_result = payload["payload"]["result"]
        return [
            f"Thermal valid: {thermal_result.thermal_valid}",
            f"Governing thermal case: {thermal_result.governing_load_case.case_name} ({thermal_result.governing_load_case.source_stage})",
            f"Governing region: {min(thermal_result.summary_margins, key=thermal_result.summary_margins.get)}",
            f"Peak throat temperature: {thermal_result.throat_result.region.peak_inner_wall_temp_k:.1f} K",
            f"Thermal protection mass: {thermal_result.total_thermal_protection_mass_estimate_kg:.3f} kg",
            f"Wrote outputs to {run_root}",
        ]
    if mode == "nozzle_offdesign":
        nozzle_result = payload["payload"]["result"]
        sea_level_summary = nozzle_result.sea_level_summary
        vacuum_summary = nozzle_result.vacuum_summary
        return [
            f"Nozzle off-design valid: {nozzle_result.nozzle_offdesign_valid}",
            f"Governing case: {nozzle_result.governing_case.case_name} ({nozzle_result.governing_case.source_stage})",
            f"Separation risk: {nozzle_result.separation_result.risk_level}",
            f"Sea-level average thrust: {'n/a' if sea_level_summary is None else f'{sea_level_summary.average_thrust_n:.1f} N'}",
            f"Vacuum average thrust: {'n/a' if vacuum_summary is None else f'{vacuum_summary.average_thrust_n:.1f} N'}",
            f"Recommended usage: {nozzle_result.recommendations.get('recommended_usage_mode')}",
            f"Wrote outputs to {run_root}",
        ]
    if mode in {"cfd_plan", "cfd_export_cases", "cfd_ingest_results", "cfd_apply_corrections"}:
        plan = payload["payload"]["plan"]
        return [
            f"CFD plan valid: {plan.cfd_plan_valid}",
            f"Recommended next CFD case: {plan.recommended_next_case_id or 'n/a'}",
            f"Case definitions: {len(payload['payload']['case_definitions'])}",
            f"Correction packages: {len(payload['payload']['correction_packages'])}",
            f"Ingested CFD summaries: {len(payload['payload']['result_summaries'])}",
            f"Wrote outputs to {run_root}",
        ]
    if mode in {"test_plan", "test_define_articles", "test_ingest_data", "test_compare_model", "test_calibrate_hotfire", "test_readiness"}:
        campaign = payload["payload"]["campaign_plan"]
        readiness = payload["payload"]["readiness"]
        return [
            f"Testing campaign valid: {campaign.test_progression_valid}",
            f"Recommended next stage: {campaign.recommended_next_stage or 'n/a'}",
            f"Recommended next test: {readiness.recommended_next_test or 'n/a'}",
            f"Model-vs-test comparisons: {len(payload['payload']['comparisons'])}",
            f"Hot-fire calibration packages: {len(payload['payload']['calibration_packages'])}",
            f"Overall readiness: {readiness.overall_readiness_flag}",
            f"Wrote outputs to {run_root}",
        ]
    metrics = payload["payload"]["metrics"]
    return [
        f"Internal ballistics status: {metrics['status']} ({metrics['stop_reason']})",
        f"Average thrust: {metrics['thrust_avg_n']:.2f} N",
        f"Impulse: {metrics['impulse_total_ns']:.2f} N s",
        f"Average Pc: {metrics['pc_avg_bar']:.2f} bar",
        f"Geometry valid: {metrics['geometry_valid']}",
        f"Wrote outputs to {run_root}",
    ]
