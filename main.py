"""Workflow entry point for CEA, 0D design studies, geometry freeze, and Step 3 ballistics."""

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
from src.constants import (
    BALLISTICS_1D_DIRNAME,
    CEA_DIRNAME,
    CORNERS_DIRNAME,
    GEOMETRY_DIRNAME,
    NOMINAL_DIRNAME,
    OUTPUT_ROOT,
    SENSITIVITY_DIRNAME,
)
from src.io_utils import ensure_directory, load_json, write_json
from src.post.ballistics_export import write_ballistics_outputs
from src.post.csv_export import write_mapping_csv, write_rows_csv
from src.post.geometry_export import write_geometry_outputs
from src.post.plotting import write_horizontal_bar_chart, write_line_plot
from src.simulation.case_runner import run_ballistics_case, run_nominal_case
from src.sizing.geometry_freeze import freeze_first_pass_geometry
from src.sizing.geometry_types import GeometryDefinition


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


def _export_geometry_run(
    study_config: Mapping[str, Any],
    cea_config_path: str | None,
    output_root: Path,
    *,
    include_step1_context: bool = True,
) -> dict[str, Any]:
    output_dir = ensure_directory(output_root / GEOMETRY_DIRNAME)
    nominal_payload = run_nominal_case(study_config)
    sensitivity_payload = run_oat_sensitivity(study_config) if include_step1_context else None
    corner_payload = run_corner_cases(study_config) if include_step1_context else None

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
            "top_sensitivity": (
                {
                    metric: rows[0] if rows else None
                    for metric, rows in sensitivity_payload["rankings"].items()
                }
                if sensitivity_payload is not None
                else {}
            ),
            "corner_cases": (
                [
                    {
                        "case_name": item["case_name"],
                        "metrics": item["metrics"],
                        "constraints": item["constraints"],
                    }
                    for item in corner_payload["corners"]
                ]
                if corner_payload is not None
                else []
            ),
            "step1_context_included": include_step1_context,
        },
    )
    write_geometry_outputs(output_dir, geometry)
    return {
        "output_dir": output_dir,
        "geometry": geometry,
    }


def _load_geometry_definition(path: Path) -> GeometryDefinition:
    return GeometryDefinition.from_mapping(load_json(path))


def _geometry_config_matches(geometry_path: Path, study_config: Mapping[str, Any]) -> bool:
    config_path = geometry_path.parent / "design_config_used.json"
    if not config_path.exists():
        return False
    try:
        return load_json(config_path) == dict(study_config)
    except Exception:
        return False


def _resolve_ballistics_geometry(
    study_config: Mapping[str, Any],
    cea_config_path: str | None,
    output_root: Path,
) -> tuple[GeometryDefinition, Path]:
    settings = study_config["ballistics_1d"]
    if settings["geometry_input_source"] == "freeze_nominal":
        payload = _export_geometry_run(study_config, cea_config_path, output_root, include_step1_context=False)
        geometry_path = payload["output_dir"] / "baseline_geometry.json"
        return payload["geometry"], geometry_path

    configured_path = Path(settings["geometry_path"])
    candidate_paths = [configured_path]
    default_output_geometry = output_root / GEOMETRY_DIRNAME / "baseline_geometry.json"
    if not configured_path.is_absolute():
        candidate_paths.append(default_output_geometry)

    for candidate in candidate_paths:
        if candidate.exists() and (
            settings["geometry_input_source"] == "file" or _geometry_config_matches(candidate, study_config)
        ):
            return _load_geometry_definition(candidate), candidate

    if settings["geometry_input_source"] == "file" and not settings["auto_freeze_geometry_if_missing"]:
        raise FileNotFoundError(f"Frozen geometry file not found: {configured_path}")

    if settings["geometry_input_source"] not in {"auto", "freeze_nominal"} and not settings["auto_freeze_geometry_if_missing"]:
        raise RuntimeError("Ballistics 1D mode requires an existing frozen geometry or auto-freeze enabled.")

    payload = _export_geometry_run(study_config, cea_config_path, output_root, include_step1_context=False)
    geometry_path = payload["output_dir"] / "baseline_geometry.json"
    return payload["geometry"], geometry_path


def _sample_station_indices(axial_history: Mapping[str, Any], station_count: int) -> list[int]:
    x_m = np.asarray(axial_history.get("x_m", []), dtype=float)
    if x_m.size == 0:
        return []
    count = max(1, min(int(station_count), len(x_m)))
    return sorted(set(int(index) for index in np.linspace(0, len(x_m) - 1, count, dtype=int)))


def _plot_ballistics_outputs(
    output_dir: Path,
    payload: Mapping[str, Any],
    zero_d_payload: Mapping[str, Any] | None = None,
) -> None:
    history = payload["result"]["history"]
    axial_history = payload["result"].get("axial_history", {})
    if not history:
        return

    time_s = history["t_s"]
    write_line_plot(
        output_dir / "pc_vs_time.svg",
        [{"label": "1D Pc [bar]", "x": time_s, "y": history["pc_bar"]}],
        "Quasi-1D Chamber Pressure vs Time",
        "Time [s]",
        "Pressure [bar]",
    )
    write_line_plot(
        output_dir / "thrust_vs_time.svg",
        [{"label": "1D Thrust [N]", "x": time_s, "y": history["thrust_n"]}],
        "Quasi-1D Thrust vs Time",
        "Time [s]",
        "Thrust [N]",
    )
    write_line_plot(
        output_dir / "of_vs_time.svg",
        [{"label": "1D O/F [-]", "x": time_s, "y": history["of_ratio"]}],
        "Quasi-1D O/F vs Time",
        "Time [s]",
        "O/F [-]",
    )
    write_line_plot(
        output_dir / "mass_flow_vs_time.svg",
        [
            {"label": "Oxidizer Flow [kg/s]", "x": time_s, "y": history["mdot_ox_kg_s"]},
            {"label": "Fuel Flow [kg/s]", "x": time_s, "y": history["mdot_f_kg_s"]},
            {"label": "Total Flow [kg/s]", "x": time_s, "y": history["mdot_total_kg_s"]},
        ],
        "Quasi-1D Mass Flow vs Time",
        "Time [s]",
        "Mass Flow [kg/s]",
    )

    if axial_history:
        axial_time_s = axial_history["time_s"]
        x_m = axial_history["x_m"]
        station_indices = _sample_station_indices(
            axial_history,
            payload["result"]["runtime"]["ballistics_settings"].station_sample_count,
        )
        radius_series = []
        gox_series = []
        for cell_index in station_indices:
            position_mm = float(x_m[cell_index] * 1000.0)
            radius_series.append(
                {
                    "label": f"x={position_mm:.0f} mm",
                    "x": axial_time_s,
                    "y": axial_history["port_radius_mm"][:, cell_index],
                }
            )
            gox_series.append(
                {
                    "label": f"x={position_mm:.0f} mm",
                    "x": axial_time_s,
                    "y": axial_history["oxidizer_flux_kg_m2_s"][:, cell_index],
                }
            )
        write_line_plot(
            output_dir / "port_radius_stations_vs_time.svg",
            radius_series,
            "Port Radius at Axial Stations",
            "Time [s]",
            "Port Radius [mm]",
        )
        write_line_plot(
            output_dir / "gox_stations_vs_time.svg",
            gox_series,
            "Oxidizer Flux at Axial Stations",
            "Time [s]",
            "Gox [kg/m^2/s]",
        )
        write_line_plot(
            output_dir / "final_port_radius_vs_x.svg",
            [{"label": "Final Port Radius [mm]", "x": x_m, "y": axial_history["port_radius_mm"][-1, :]}],
            "Final Port Radius vs Axial Position",
            "Axial Position [m]",
            "Port Radius [mm]",
        )
        write_line_plot(
            output_dir / "final_regression_rate_vs_x.svg",
            [{"label": "Final rdot [mm/s]", "x": x_m, "y": axial_history["regression_rate_mm_s"][-1, :]}],
            "Final Regression Rate vs Axial Position",
            "Axial Position [m]",
            "Regression Rate [mm/s]",
        )

    if zero_d_payload is not None and zero_d_payload["result"]["history"]:
        zero_d_history = zero_d_payload["result"]["history"]
        write_line_plot(
            output_dir / "compare_pc_0d_vs_1d.svg",
            [
                {"label": "0D", "x": zero_d_history["t_s"], "y": zero_d_history["pc_bar"]},
                {"label": "1D", "x": history["t_s"], "y": history["pc_bar"]},
            ],
            "0D vs 1D | Chamber Pressure",
            "Time [s]",
            "Pressure [bar]",
        )
        write_line_plot(
            output_dir / "compare_thrust_0d_vs_1d.svg",
            [
                {"label": "0D", "x": zero_d_history["t_s"], "y": zero_d_history["thrust_n"]},
                {"label": "1D", "x": history["t_s"], "y": history["thrust_n"]},
            ],
            "0D vs 1D | Thrust",
            "Time [s]",
            "Thrust [N]",
        )
        write_line_plot(
            output_dir / "compare_of_0d_vs_1d.svg",
            [
                {"label": "0D", "x": zero_d_history["t_s"], "y": zero_d_history["of_ratio"]},
                {"label": "1D", "x": history["t_s"], "y": history["of_ratio"]},
            ],
            "0D vs 1D | O/F",
            "Time [s]",
            "O/F [-]",
        )


def _export_ballistics_run(study_config: Mapping[str, Any], cea_config_path: str | None, output_root: Path) -> dict[str, Any]:
    output_dir = ensure_directory(output_root / BALLISTICS_1D_DIRNAME)
    geometry, geometry_path = _resolve_ballistics_geometry(study_config, cea_config_path, output_root)
    raw_cea_config = load_cea_config(cea_config_path) if cea_config_path else None
    zero_d_payload = run_nominal_case(study_config) if study_config["ballistics_1d"]["compare_to_0d"] else None
    payload = run_ballistics_case(
        study_config,
        geometry,
        cea_data={"raw_config": raw_cea_config} if raw_cea_config is not None else None,
        compare_payload=zero_d_payload,
    )

    write_json(output_dir / "design_config_used.json", study_config)
    write_json(output_dir / "baseline_geometry_used.json", geometry.to_dict())
    write_json(output_dir / "ballistics_settings_used.json", study_config["ballistics_1d"])
    write_json(output_dir / "geometry_source.json", {"geometry_path": str(geometry_path)})
    if raw_cea_config is not None:
        write_json(output_dir / "cea_config_used.json", raw_cea_config)
    if zero_d_payload is not None:
        write_json(output_dir / "nominal_0d_metrics.json", zero_d_payload["metrics"])
    write_ballistics_outputs(
        output_dir,
        result=payload["result"],
        metrics=payload["metrics"],
        constraints=payload["constraints"],
        geometry=geometry,
        comparison=payload["comparison"],
    )
    _plot_ballistics_outputs(output_dir, payload, zero_d_payload=zero_d_payload)
    return {
        "output_dir": output_dir,
        "payload": payload,
        "geometry": geometry,
        "zero_d_payload": zero_d_payload,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hybrid rocket workflow entry point.")
    parser.add_argument(
        "--mode",
        required=True,
        choices=["cea", "nominal", "oat", "corners", "freeze_geometry", "ballistics_1d"],
        help="Workflow mode to execute.",
    )
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

    if args.mode == "freeze_geometry":
        payload = _export_geometry_run(study_config, args.cea_config, output_root)
        geometry = payload["geometry"]
        print(f"Frozen geometry valid: {geometry.geometry_valid}")
        print(f"Chamber ID: {geometry.chamber_id_m * 1000.0:.2f} mm")
        print(f"Grain length: {geometry.grain_length_m * 1000.0:.2f} mm")
        print(f"Throat diameter: {geometry.throat_diameter_m * 1000.0:.2f} mm")
        print(f"Initial L*: {geometry.lstar_initial_m:.3f} m")
        print(f"Wrote outputs to {payload['output_dir']}")
        return

    payload = _export_ballistics_run(study_config, args.cea_config, output_root)
    metrics = payload["payload"]["metrics"]
    print(f"Ballistics 1D status: {metrics['status']} ({metrics['stop_reason']})")
    print(f"Average thrust: {metrics['thrust_avg_n']:.2f} N")
    print(f"Impulse: {metrics['impulse_total_ns']:.2f} N s")
    print(f"Average Pc: {metrics['pc_avg_bar']:.2f} bar")
    print(f"Geometry valid: {metrics['geometry_valid']}")
    print(f"Wrote outputs to {payload['output_dir']}")


if __name__ == "__main__":
    main()
