"""Workflow entry point for CEA studies and Step 1 0D design analysis."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from src.analysis.corner_cases import run_corner_cases
from src.analysis.sensitivity import run_oat_sensitivity
from src.analysis.summaries import constraint_rows, metrics_to_row
from src.cea.cea_interface import get_cea_performance_point, load_cea_config, run_cea_case, run_cea_study, write_cea_outputs
from src.config_schema import build_design_config, load_design_config
from src.constants import CEA_DIRNAME, CORNERS_DIRNAME, GEOMETRY_DIRNAME, NOMINAL_DIRNAME, OUTPUT_ROOT, SENSITIVITY_DIRNAME
from src.io_utils import ensure_directory, write_json
from src.post.csv_export import write_mapping_csv, write_rows_csv
from src.post.geometry_export import write_geometry_outputs
from src.post.plotting import write_horizontal_bar_chart, write_line_plot
from src.simulation.case_runner import run_nominal_case
from src.sizing.geometry_freeze import freeze_first_pass_geometry


def _coerce_scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    return value


def _history_rows(history: Mapping[str, Any]) -> list[dict[str, Any]]:
    time_s = np.asarray(history.get("t_s", []), dtype=float)
    rows: list[dict[str, Any]] = []
    if time_s.size == 0:
        return rows

    series_keys = []
    for key, value in history.items():
        if isinstance(value, np.ndarray) and len(value) == len(time_s):
            series_keys.append(key)

    for index in range(len(time_s)):
        row = {key: _coerce_scalar(history[key][index]) for key in series_keys}
        rows.append(row)
    return rows


def _plot_nominal_outputs(output_dir: Path, history: Mapping[str, Any]) -> None:
    time_s = history["t_s"]
    write_line_plot(
        output_dir / "pc_vs_time.svg",
        [{"label": "Pc [bar]", "x": time_s, "y": history["pc_bar"]}],
        "Chamber Pressure vs Time",
        "Time [s]",
        "Pressure [bar]",
    )
    write_line_plot(
        output_dir / "thrust_vs_time.svg",
        [{"label": "Thrust [N]", "x": time_s, "y": history["thrust_n"]}],
        "Thrust vs Time",
        "Time [s]",
        "Thrust [N]",
    )
    write_line_plot(
        output_dir / "mass_flow_vs_time.svg",
        [
            {"label": "Oxidizer Flow [kg/s]", "x": time_s, "y": history["mdot_ox_kg_s"]},
            {"label": "Fuel Flow [kg/s]", "x": time_s, "y": history["mdot_f_kg_s"]},
        ],
        "Mass Flow vs Time",
        "Time [s]",
        "Mass Flow [kg/s]",
    )
    write_line_plot(
        output_dir / "of_vs_time.svg",
        [{"label": "O/F [-]", "x": time_s, "y": history["of_ratio"]}],
        "O/F vs Time",
        "Time [s]",
        "O/F [-]",
    )
    write_line_plot(
        output_dir / "port_radius_vs_time.svg",
        [{"label": "Port Radius [mm]", "x": time_s, "y": history["port_radius_mm"]}],
        "Port Radius vs Time",
        "Time [s]",
        "Port Radius [mm]",
    )
    write_line_plot(
        output_dir / "tank_pressure_vs_time.svg",
        [{"label": "Tank Pressure [bar]", "x": time_s, "y": history["tank_pressure_bar"]}],
        "Tank Pressure vs Time",
        "Time [s]",
        "Pressure [bar]",
    )


def _export_nominal_run(study_config: Mapping[str, Any], output_root: Path) -> dict[str, Any]:
    output_dir = ensure_directory(output_root / NOMINAL_DIRNAME)
    payload = run_nominal_case(study_config)
    result = payload["result"]
    metrics = payload["metrics"]
    constraints = payload["constraints"]

    write_json(output_dir / "design_config_used.json", study_config)
    write_rows_csv(output_dir / "nominal_history.csv", _history_rows(result["history"]))
    write_mapping_csv(output_dir / "nominal_metrics.csv", metrics)
    write_rows_csv(output_dir / "nominal_constraints.csv", constraint_rows(constraints))
    write_json(output_dir / "nominal_metrics.json", metrics)
    write_json(output_dir / "nominal_constraints.json", constraints)
    if result["history"]:
        _plot_nominal_outputs(output_dir, result["history"])
    return payload


def _export_sensitivity_run(study_config: Mapping[str, Any], output_root: Path) -> dict[str, Any]:
    output_dir = ensure_directory(output_root / SENSITIVITY_DIRNAME)
    payload = run_oat_sensitivity(study_config)
    write_json(output_dir / "design_config_used.json", payload["config"])
    write_rows_csv(output_dir / "oat_cases.csv", payload["cases"])
    write_json(output_dir / "nominal_metrics.json", payload["nominal"]["metrics"])
    for metric, rows in payload["rankings"].items():
        write_rows_csv(output_dir / f"ranking_{metric}.csv", rows)
        chart_entries = [
            {"label": row["parameter"], "value": row["normalized_sensitivity_abs"] or 0.0}
            for row in rows
        ]
        write_horizontal_bar_chart(
            output_dir / f"ranking_{metric}.svg",
            chart_entries,
            f"Normalized Sensitivity Ranking | {metric}",
            "Absolute normalized sensitivity [-]",
        )
    return payload


def _overlay_series(nominal_history: Mapping[str, Any], corner_payloads: Iterable[Mapping[str, Any]], history_key: str) -> list[dict[str, Any]]:
    series = [{"label": "nominal", "x": nominal_history["t_s"], "y": nominal_history[history_key]}]
    for payload in corner_payloads:
        history = payload["result"]["history"]
        if not history:
            continue
        series.append({"label": payload["case_name"], "x": history["t_s"], "y": history[history_key]})
    return series


def _export_corner_run(study_config: Mapping[str, Any], output_root: Path) -> dict[str, Any]:
    output_dir = ensure_directory(output_root / CORNERS_DIRNAME)
    payload = run_corner_cases(study_config)
    write_json(output_dir / "design_config_used.json", payload["config"])

    summary_rows = [
        metrics_to_row("nominal", payload["nominal"]["metrics"], payload["nominal"]["constraints"]),
        *[
            metrics_to_row(item["case_name"], item["metrics"], item["constraints"])
            for item in payload["corners"]
        ],
    ]
    write_rows_csv(output_dir / "corner_case_summary.csv", summary_rows)
    write_json(output_dir / "corner_case_summary.json", {"cases": summary_rows})

    nominal_history = payload["nominal"]["result"]["history"]
    if nominal_history:
        write_line_plot(
            output_dir / "pc_overlay.svg",
            _overlay_series(nominal_history, payload["corners"], "pc_bar"),
            "Corner Case Overlay | Chamber Pressure",
            "Time [s]",
            "Pressure [bar]",
        )
        write_line_plot(
            output_dir / "thrust_overlay.svg",
            _overlay_series(nominal_history, payload["corners"], "thrust_n"),
            "Corner Case Overlay | Thrust",
            "Time [s]",
            "Thrust [N]",
        )
        write_line_plot(
            output_dir / "of_overlay.svg",
            _overlay_series(nominal_history, payload["corners"], "of_ratio"),
            "Corner Case Overlay | O/F",
            "Time [s]",
            "O/F [-]",
        )
    return payload


def _run_cea_mode(cea_config_path: str | None, output_root: Path) -> dict[str, Any]:
    output_dir = ensure_directory(output_root / CEA_DIRNAME)
    raw_config = load_cea_config(cea_config_path)
    sweep_result = run_cea_study(raw_config)
    write_json(output_dir / "cea_config_used.json", raw_config)
    write_cea_outputs(output_dir, raw_config, sweep_result)
    highest_isp = get_cea_performance_point(sweep_result)
    write_json(output_dir / "highest_isp_case.json", highest_isp.raw)
    return {
        "output_dir": output_dir,
        "case_count": len(sweep_result.cases),
        "failure_count": len(sweep_result.failures),
        "best_isp_s": highest_isp.isp_s,
    }


def _build_nominal_cea_case_input(study_config: Mapping[str, Any], cea_config: Mapping[str, Any]) -> dict[str, Any]:
    performance = study_config["nominal"]["performance"]
    return {
        "target_thrust_n": float(performance["target_thrust_n"]),
        "max_exit_diameter_cm": float(cea_config["max_exit_diameter_cm"]),
        "max_area_ratio": float(cea_config.get("max_area_ratio", 24.0)),
        "ae_at_cap_mode": cea_config.get("ae_at_cap_mode", "exit_diameter"),
        "pc_bar": float(performance["pc_bar"]),
        "abs_vol_frac": float(performance["abs_volume_fraction"]),
        "fuel_temp_k": float(performance["fuel_temperature_k"]),
        "oxidizer_temp_k": float(performance["tank_temperature_k"]),
        "of": float(performance["of_ratio"]),
        "ae_at": float(performance["ae_at"]),
    }


def _export_geometry_run(study_config: Mapping[str, Any], cea_config_path: str | None, output_root: Path) -> dict[str, Any]:
    output_dir = ensure_directory(output_root / GEOMETRY_DIRNAME)
    nominal_payload = run_nominal_case(study_config)
    sensitivity_payload = run_oat_sensitivity(study_config)
    corner_payload = run_corner_cases(study_config)

    cea_reference = None
    cea_warning = None
    try:
        raw_cea_config = load_cea_config(cea_config_path)
        if study_config["geometry_policy"].get("use_nominal_case_for_cea_reference", True):
            cea_reference = run_cea_case(
                {
                    "base_config": raw_cea_config,
                    "case_input": _build_nominal_cea_case_input(study_config, raw_cea_config),
                }
            )
        else:
            cea_reference = get_cea_performance_point(run_cea_study(raw_cea_config))
    except Exception as exc:
        cea_warning = f"CEA reference unavailable during geometry freeze: {exc}"

    geometry = freeze_first_pass_geometry(
        study_config,
        cea_reference,
        nominal_payload,
        sensitivity_summary=sensitivity_payload,
        corner_summary=corner_payload,
    )
    if cea_warning:
        geometry = replace(geometry, warnings=[*geometry.warnings, cea_warning])

    write_json(output_dir / "design_config_used.json", study_config)
    if cea_reference is not None:
        write_json(output_dir / "cea_reference_case.json", cea_reference.raw)
    write_json(
        output_dir / "geometry_context.json",
        {
            "nominal_metrics": nominal_payload["metrics"],
            "nominal_constraints": nominal_payload["constraints"],
            "top_sensitivity": {
                metric: rows[0] if rows else None
                for metric, rows in sensitivity_payload["rankings"].items()
            },
            "corner_cases": [
                {
                    "case_name": item["case_name"],
                    "metrics": item["metrics"],
                    "constraints": item["constraints"],
                }
                for item in corner_payload["corners"]
            ],
        },
    )
    write_geometry_outputs(output_dir, geometry)
    return {
        "output_dir": output_dir,
        "geometry": geometry,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hybrid rocket workflow entry point.")
    parser.add_argument("--mode", required=True, choices=["cea", "nominal", "oat", "corners", "freeze_geometry"], help="Workflow mode to execute.")
    parser.add_argument("--config", default=None, help="Optional path to a design-study override JSON config.")
    parser.add_argument("--cea-config", dest="cea_config", default=None, help="Optional path to a CEA override JSON config.")
    parser.add_argument("--output-dir", default=str(OUTPUT_ROOT), help="Root output directory for generated artifacts.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_root = ensure_directory(args.output_dir)

    if args.mode == "cea":
        summary = _run_cea_mode(args.cea_config, output_root)
        print(f"CEA sweep completed: {summary['case_count']} converged case(s), {summary['failure_count']} failure(s).")
        print(f"Highest-Isp case: {summary['best_isp_s']:.3f} s")
        print(f"Wrote outputs to {summary['output_dir']}")
        return

    study_config = load_design_config(args.config) if args.config else build_design_config()
    if args.mode == "nominal":
        payload = _export_nominal_run(study_config, output_root)
        print(f"Nominal case status: {payload['metrics']['status']} ({payload['metrics']['stop_reason']})")
        print(f"Average thrust: {payload['metrics']['thrust_avg_n']:.2f} N")
        print(f"Impulse: {payload['metrics']['impulse_total_ns']:.2f} N s")
        print(f"Constraints pass: {payload['constraints']['all_pass']}")
        print(f"Wrote outputs to {output_root / NOMINAL_DIRNAME}")
        return

    if args.mode == "oat":
        payload = _export_sensitivity_run(study_config, output_root)
        print(f"OAT sensitivity completed for {len(payload['cases'])} case variants.")
        print(f"Wrote outputs to {output_root / SENSITIVITY_DIRNAME}")
        return

    if args.mode == "corners":
        payload = _export_corner_run(study_config, output_root)
        print(f"Corner-case study completed for {len(payload['corners'])} named corner cases.")
        print(f"Wrote outputs to {output_root / CORNERS_DIRNAME}")
        return

    payload = _export_geometry_run(study_config, args.cea_config, output_root)
    geometry = payload["geometry"]
    print(f"Frozen geometry valid: {geometry.geometry_valid}")
    print(f"Chamber ID: {geometry.chamber_id_m * 1000.0:.2f} mm")
    print(f"Grain length: {geometry.grain_length_m * 1000.0:.2f} mm")
    print(f"Throat diameter: {geometry.throat_diameter_m * 1000.0:.2f} mm")
    print(f"Initial L*: {geometry.lstar_initial_m:.3f} m")
    print(f"Wrote outputs to {payload['output_dir']}")


if __name__ == "__main__":
    main()
