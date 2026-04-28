"""Shared workflow export and dependency helpers."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from src.analysis.corner_cases import run_corner_cases
from src.analysis.sensitivity import run_oat_sensitivity
from src.analysis.summaries import constraint_rows, metrics_to_row
from src.cea.cea_interface import get_cea_performance_point, load_cea_config, run_cea_case, run_cea_study, write_cea_outputs
from src.constants import (
    ANALYSIS_DIRNAME,
    CFD_DIRNAME,
    GEOMETRY_DIRNAME,
    HYDRAULIC_VALIDATION_DIRNAME,
    INJECTOR_DESIGN_DIRNAME,
    INTERNAL_BALLISTICS_DIRNAME,
    NOZZLE_OFFDESIGN_DIRNAME,
    PERFORMANCE_DIRNAME,
    STRUCTURAL_DIRNAME,
    TESTING_DIRNAME,
    THERMAL_DIRNAME,
    THERMOCHEMISTRY_DIRNAME,
)
from src.cfd import run_cfd_workflow
from src.injector_design import build_injector_synthesis_case, load_injector_geometry_definition, write_injector_outputs
from src.io_utils import ensure_directory, load_json, write_json
from src.nozzle_offdesign import run_nozzle_offdesign_workflow
from src.post.ballistics_export import write_ballistics_outputs
from src.post.csv_export import write_mapping_csv, write_rows_csv
from src.post.geometry_export import write_geometry_outputs
from src.post.plotting import write_horizontal_bar_chart, write_line_plot
from src.structural import run_structural_sizing_workflow
from src.testing import run_testing_workflow
from src.thermal import run_thermal_sizing_workflow
from src.simulation.case_runner import run_internal_ballistics_case, run_nominal_case
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
    output_dir = ensure_directory(output_root / PERFORMANCE_DIRNAME)
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
    return {**payload, "output_dir": output_dir}


def _export_sensitivity_run(study_config: Mapping[str, Any], output_root: Path) -> dict[str, Any]:
    output_dir = ensure_directory(output_root / ANALYSIS_DIRNAME / "sensitivity")
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
    return {**payload, "output_dir": output_dir}


def _overlay_series(nominal_history: Mapping[str, Any], corner_payloads: Iterable[Mapping[str, Any]], history_key: str) -> list[dict[str, Any]]:
    series = [{"label": "nominal", "x": nominal_history["t_s"], "y": nominal_history[history_key]}]
    for payload in corner_payloads:
        history = payload["result"]["history"]
        if not history:
            continue
        series.append({"label": payload["case_name"], "x": history["t_s"], "y": history[history_key]})
    return series


def _export_corner_run(study_config: Mapping[str, Any], output_root: Path) -> dict[str, Any]:
    output_dir = ensure_directory(output_root / ANALYSIS_DIRNAME / "corners")
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
    return {**payload, "output_dir": output_dir}


def _run_cea_mode(cea_config_path: str | None, output_root: Path) -> dict[str, Any]:
    output_dir = ensure_directory(output_root / THERMOCHEMISTRY_DIRNAME)
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


def _resolved_cea_config(
    cea_config_path: str | None,
    cea_config_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if cea_config_override is not None:
        return deepcopy(dict(cea_config_override))
    return load_cea_config(cea_config_path)


def _export_geometry_run(
    study_config: Mapping[str, Any],
    cea_config_path: str | None,
    output_root: Path,
    *,
    cea_config_override: Mapping[str, Any] | None = None,
    include_analysis_context: bool = True,
) -> dict[str, Any]:
    output_dir = ensure_directory(output_root / GEOMETRY_DIRNAME)
    baseline_config = deepcopy(dict(study_config))
    baseline_config.setdefault("injector_design", {})["solver_injector_source"] = "equivalent_manual"

    nominal_payload = run_nominal_case(baseline_config, injector_source_override="equivalent_manual")
    sensitivity_payload = run_oat_sensitivity(baseline_config) if include_analysis_context else None
    corner_payload = run_corner_cases(baseline_config) if include_analysis_context else None

    cea_reference = None
    cea_warning = None
    try:
        raw_cea_config = _resolved_cea_config(cea_config_path, cea_config_override)
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
            "analysis_context_included": include_analysis_context,
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
    *,
    cea_config_override: Mapping[str, Any] | None = None,
) -> tuple[GeometryDefinition, Path]:
    settings = study_config["internal_ballistics"]
    if settings["geometry_input_source"] == "freeze_nominal":
        payload = _export_geometry_run(
            study_config,
            cea_config_path,
            output_root,
            cea_config_override=cea_config_override,
            include_analysis_context=False,
        )
        geometry_path = payload["output_dir"] / "geometry_definition.json"
        return payload["geometry"], geometry_path

    configured_path = Path(settings["geometry_path"])
    candidate_paths = [configured_path]
    default_output_geometry = output_root / GEOMETRY_DIRNAME / "geometry_definition.json"
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

    payload = _export_geometry_run(
        study_config,
        cea_config_path,
        output_root,
        cea_config_override=cea_config_override,
        include_analysis_context=False,
    )
    geometry_path = payload["output_dir"] / "geometry_definition.json"
    return payload["geometry"], geometry_path


def _resolve_injector_engine_geometry(
    study_config: Mapping[str, Any],
    cea_config_path: str | None,
    output_root: Path,
    *,
    cea_config_override: Mapping[str, Any] | None = None,
) -> tuple[GeometryDefinition, Path]:
    settings = study_config["injector_design"]
    if settings["engine_geometry_input_source"] == "freeze_nominal":
        payload = _export_geometry_run(
            study_config,
            cea_config_path,
            output_root,
            cea_config_override=cea_config_override,
            include_analysis_context=False,
        )
        geometry_path = payload["output_dir"] / "geometry_definition.json"
        return payload["geometry"], geometry_path

    configured_path = Path(settings["engine_geometry_path"])
    candidate_paths = [configured_path]
    default_output_geometry = output_root / GEOMETRY_DIRNAME / "geometry_definition.json"
    if not configured_path.is_absolute():
        candidate_paths.append(default_output_geometry)

    for candidate in candidate_paths:
        if candidate.exists() and (
            settings["engine_geometry_input_source"] == "file" or _geometry_config_matches(candidate, study_config)
        ):
            return _load_geometry_definition(candidate), candidate

    if settings["engine_geometry_input_source"] == "file" and not settings["auto_freeze_geometry_if_missing"]:
        raise FileNotFoundError(f"Frozen geometry file not found: {configured_path}")

    if settings["engine_geometry_input_source"] != "auto" and not settings["auto_freeze_geometry_if_missing"]:
        raise RuntimeError("Injector synthesis requires an existing frozen geometry or auto-freeze enabled.")

    payload = _export_geometry_run(
        study_config,
        cea_config_path,
        output_root,
        cea_config_override=cea_config_override,
        include_analysis_context=False,
    )
    geometry_path = payload["output_dir"] / "geometry_definition.json"
    return payload["geometry"], geometry_path


def _resolve_structural_geometry(
    study_config: Mapping[str, Any],
    cea_config_path: str | None,
    output_root: Path,
    *,
    cea_config_override: Mapping[str, Any] | None = None,
) -> tuple[GeometryDefinition, Path]:
    settings = study_config["structural"]
    if settings["geometry_input_source"] == "freeze_nominal":
        payload = _export_geometry_run(
            study_config,
            cea_config_path,
            output_root,
            cea_config_override=cea_config_override,
            include_analysis_context=False,
        )
        geometry_path = payload["output_dir"] / "geometry_definition.json"
        return payload["geometry"], geometry_path

    configured_path = Path(settings["geometry_path"])
    candidate_paths = [configured_path]
    default_output_geometry = output_root / GEOMETRY_DIRNAME / "geometry_definition.json"
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
        raise RuntimeError("Structural sizing requires an existing frozen geometry or auto-freeze enabled.")

    payload = _export_geometry_run(
        study_config,
        cea_config_path,
        output_root,
        cea_config_override=cea_config_override,
        include_analysis_context=False,
    )
    geometry_path = payload["output_dir"] / "geometry_definition.json"
    return payload["geometry"], geometry_path


def _resolve_structural_injector_geometry(
    study_config: Mapping[str, Any],
    geometry: GeometryDefinition,
    cea_config_path: str | None,
    output_root: Path,
    *,
    cea_config_override: Mapping[str, Any] | None = None,
):
    settings = study_config["structural"]
    source = settings["injector_geometry_input_source"]
    if source == "disabled":
        return None, None

    configured_path = Path(settings["injector_geometry_path"])
    candidate_paths = [configured_path]
    default_output_injector = output_root / INJECTOR_DESIGN_DIRNAME / "injector_geometry.json"
    if not configured_path.is_absolute():
        candidate_paths.append(default_output_injector)

    for candidate in candidate_paths:
        if candidate.exists():
            return load_injector_geometry_definition(candidate), candidate

    if source == "file" and not settings["auto_synthesize_injector_if_missing"]:
        if settings["allow_missing_injector_geometry"]:
            return None, None
        raise FileNotFoundError(f"Injector geometry file not found: {configured_path}")

    if source == "auto" and not settings["auto_synthesize_injector_if_missing"]:
        if settings["allow_missing_injector_geometry"]:
            return None, None
        raise RuntimeError("Structural sizing requested injector geometry, but synthesis fallback is disabled.")

    raw_cea_config = _resolved_cea_config(cea_config_path, cea_config_override) if (cea_config_path or cea_config_override) else None
    synthesis = build_injector_synthesis_case(
        study_config,
        geometry,
        raw_cea_config=raw_cea_config,
    )
    return synthesis["injector_geometry"], None


def _resolve_nozzle_offdesign_geometry(
    study_config: Mapping[str, Any],
    cea_config_path: str | None,
    output_root: Path,
    *,
    cea_config_override: Mapping[str, Any] | None = None,
) -> tuple[GeometryDefinition, Path]:
    settings = study_config["nozzle_offdesign"]
    if settings["geometry_input_source"] == "freeze_nominal":
        payload = _export_geometry_run(
            study_config,
            cea_config_path,
            output_root,
            cea_config_override=cea_config_override,
            include_analysis_context=False,
        )
        geometry_path = payload["output_dir"] / "geometry_definition.json"
        return payload["geometry"], geometry_path

    configured_path = Path(settings["geometry_path"])
    candidate_paths = [configured_path]
    default_output_geometry = output_root / GEOMETRY_DIRNAME / "geometry_definition.json"
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
        raise RuntimeError("Nozzle off-design evaluation requires an existing frozen geometry or auto-freeze enabled.")

    payload = _export_geometry_run(
        study_config,
        cea_config_path,
        output_root,
        cea_config_override=cea_config_override,
        include_analysis_context=False,
    )
    geometry_path = payload["output_dir"] / "geometry_definition.json"
    return payload["geometry"], geometry_path


def _resolve_nozzle_offdesign_injector_geometry(
    study_config: Mapping[str, Any],
    geometry: GeometryDefinition,
    cea_config_path: str | None,
    output_root: Path,
    *,
    cea_config_override: Mapping[str, Any] | None = None,
):
    settings = study_config["nozzle_offdesign"]
    source = settings["injector_geometry_input_source"]
    if source == "disabled":
        return None, None

    configured_path = Path(settings["injector_geometry_path"])
    candidate_paths = [configured_path]
    default_output_injector = output_root / INJECTOR_DESIGN_DIRNAME / "injector_geometry.json"
    if not configured_path.is_absolute():
        candidate_paths.append(default_output_injector)

    for candidate in candidate_paths:
        if candidate.exists():
            return load_injector_geometry_definition(candidate), candidate

    if source == "file" and not settings["auto_synthesize_injector_if_missing"]:
        if settings["allow_missing_injector_geometry"]:
            return None, None
        raise FileNotFoundError(f"Injector geometry file not found: {configured_path}")

    if source == "auto" and not settings["auto_synthesize_injector_if_missing"]:
        if settings["allow_missing_injector_geometry"]:
            return None, None
        raise RuntimeError("Nozzle off-design evaluation requested injector geometry, but synthesis fallback is disabled.")

    raw_cea_config = _resolved_cea_config(cea_config_path, cea_config_override) if (cea_config_path or cea_config_override) else None
    synthesis = build_injector_synthesis_case(
        study_config,
        geometry,
        raw_cea_config=raw_cea_config,
    )
    return synthesis["injector_geometry"], None


def _resolve_cfd_geometry(
    study_config: Mapping[str, Any],
    cea_config_path: str | None,
    output_root: Path,
    *,
    cea_config_override: Mapping[str, Any] | None = None,
) -> tuple[GeometryDefinition, Path]:
    settings = study_config["cfd"]
    if settings["geometry_input_source"] == "freeze_nominal":
        payload = _export_geometry_run(
            study_config,
            cea_config_path,
            output_root,
            cea_config_override=cea_config_override,
            include_analysis_context=False,
        )
        geometry_path = payload["output_dir"] / "geometry_definition.json"
        return payload["geometry"], geometry_path

    configured_path = Path(settings["geometry_path"])
    candidate_paths = [configured_path]
    default_output_geometry = output_root / GEOMETRY_DIRNAME / "geometry_definition.json"
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
        raise RuntimeError("CFD workflow requires an existing frozen geometry or auto-freeze enabled.")

    payload = _export_geometry_run(
        study_config,
        cea_config_path,
        output_root,
        cea_config_override=cea_config_override,
        include_analysis_context=False,
    )
    geometry_path = payload["output_dir"] / "geometry_definition.json"
    return payload["geometry"], geometry_path


def _resolve_cfd_injector_geometry(
    study_config: Mapping[str, Any],
    geometry: GeometryDefinition,
    cea_config_path: str | None,
    output_root: Path,
    *,
    cea_config_override: Mapping[str, Any] | None = None,
):
    settings = study_config["cfd"]
    source = settings["injector_geometry_input_source"]
    if source == "disabled":
        return None, None

    configured_path = Path(settings["injector_geometry_path"])
    candidate_paths = [configured_path]
    default_output_injector = output_root / INJECTOR_DESIGN_DIRNAME / "injector_geometry.json"
    if not configured_path.is_absolute():
        candidate_paths.append(default_output_injector)

    for candidate in candidate_paths:
        if candidate.exists():
            return load_injector_geometry_definition(candidate), candidate

    if source == "file" and not settings["auto_synthesize_injector_if_missing"]:
        if settings["allow_missing_injector_geometry"]:
            return None, None
        raise FileNotFoundError(f"Injector geometry file not found: {configured_path}")

    if source == "auto" and not settings["auto_synthesize_injector_if_missing"]:
        if settings["allow_missing_injector_geometry"]:
            return None, None
        raise RuntimeError("CFD workflow requested injector geometry, but synthesis fallback is disabled.")

    raw_cea_config = _resolved_cea_config(cea_config_path, cea_config_override) if (cea_config_path or cea_config_override) else None
    synthesis = build_injector_synthesis_case(
        study_config,
        geometry,
        raw_cea_config=raw_cea_config,
    )
    return synthesis["injector_geometry"], None


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


def _export_ballistics_run(
    study_config: Mapping[str, Any],
    cea_config_path: str | None,
    output_root: Path,
    *,
    cea_config_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    output_dir = ensure_directory(output_root / INTERNAL_BALLISTICS_DIRNAME)
    geometry, geometry_path = _resolve_ballistics_geometry(
        study_config,
        cea_config_path,
        output_root,
        cea_config_override=cea_config_override,
    )
    raw_cea_config = _resolved_cea_config(cea_config_path, cea_config_override) if (cea_config_path or cea_config_override) else None
    zero_d_payload = (
        run_nominal_case(study_config, frozen_geometry=geometry, raw_cea_config=raw_cea_config)
        if study_config["internal_ballistics"]["compare_to_0d"]
        else None
    )
    payload = run_internal_ballistics_case(
        study_config,
        geometry,
        cea_data={"raw_config": raw_cea_config} if raw_cea_config is not None else None,
        compare_payload=zero_d_payload,
    )

    write_json(output_dir / "design_config_used.json", study_config)
    write_json(output_dir / "geometry_definition_used.json", geometry.to_dict())
    write_json(output_dir / "internal_ballistics_settings_used.json", study_config["internal_ballistics"])
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


def _export_injector_run(
    study_config: Mapping[str, Any],
    cea_config_path: str | None,
    output_root: Path,
    *,
    cea_config_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    output_dir = ensure_directory(output_root / INJECTOR_DESIGN_DIRNAME)
    engine_geometry, geometry_path = _resolve_injector_engine_geometry(
        study_config,
        cea_config_path,
        output_root,
        cea_config_override=cea_config_override,
    )
    raw_cea_config = _resolved_cea_config(cea_config_path, cea_config_override) if (cea_config_path or cea_config_override) else None

    nominal_payload = None
    if study_config["injector_design"]["design_condition_source"] in {"nominal_average", "hot_case"}:
        nominal_payload = run_nominal_case(
            study_config,
            frozen_geometry=engine_geometry,
            injector_source_override="equivalent_manual",
            raw_cea_config=raw_cea_config,
        )

    synthesis = build_injector_synthesis_case(
        study_config,
        engine_geometry,
        nominal_payload=nominal_payload,
        raw_cea_config=raw_cea_config,
    )
    write_json(output_dir / "design_config_used.json", study_config)
    write_json(output_dir / "injector_settings_used.json", study_config["injector_design"])
    write_json(output_dir / "geometry_definition_used.json", engine_geometry.to_dict())
    write_json(output_dir / "geometry_source.json", {"geometry_path": str(geometry_path)})
    if raw_cea_config is not None:
        write_json(output_dir / "cea_config_used.json", raw_cea_config)
    if nominal_payload is not None:
        write_json(output_dir / "nominal_0d_metrics.json", nominal_payload["metrics"])
    write_injector_outputs(
        output_dir,
        engine_geometry=engine_geometry,
        design_point=synthesis["design_point"],
        requirement=synthesis["requirement"].to_dict(),
        injector_geometry=synthesis["injector_geometry"],
        effective_model=synthesis["effective_model"],
        candidates=synthesis["candidates"],
    )
    return {
        "output_dir": output_dir,
        "engine_geometry": engine_geometry,
        "payload": synthesis,
        "nominal_payload": nominal_payload,
    }


def _export_structural_run(
    study_config: Mapping[str, Any],
    structural_config: Mapping[str, Any],
    cea_config_path: str | None,
    output_root: Path,
    *,
    cea_config_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    output_dir = ensure_directory(output_root / STRUCTURAL_DIRNAME)
    geometry, geometry_path = _resolve_structural_geometry(
        study_config,
        cea_config_path,
        output_root,
        cea_config_override=cea_config_override,
    )
    injector_geometry, injector_geometry_path = _resolve_structural_injector_geometry(
        study_config,
        geometry,
        cea_config_path,
        output_root,
        cea_config_override=cea_config_override,
    )
    raw_cea_config = _resolved_cea_config(cea_config_path, cea_config_override) if (cea_config_path or cea_config_override) else None
    nominal_payload = run_nominal_case(
        study_config,
        frozen_geometry=geometry,
        injector_geometry=injector_geometry,
        raw_cea_config=raw_cea_config,
    )

    corner_payload = None
    if structural_config["load_source"] == "corner_case_envelope" or structural_config["include_corner_case_envelope"]:
        corner_payload = run_corner_cases(
            study_config,
            frozen_geometry=geometry,
            injector_geometry=injector_geometry,
            raw_cea_config=raw_cea_config,
        )

    ballistics_payload = None
    if structural_config["load_source"] == "peak_1d" or structural_config["include_internal_ballistics_peak_case"]:
        ballistics_payload = run_internal_ballistics_case(
            study_config,
            geometry,
            cea_data={"raw_config": raw_cea_config} if raw_cea_config is not None else None,
            injector_geometry=injector_geometry,
        )

    payload = run_structural_sizing_workflow(
        study_config,
        structural_config,
        str(output_dir),
        geometry=geometry,
        nominal_payload=nominal_payload,
        injector_geometry=injector_geometry,
        corner_payload=corner_payload,
        ballistics_payload=ballistics_payload,
    )
    write_json(output_dir / "design_config_used.json", study_config)
    write_json(output_dir / "structural_settings_used.json", structural_config)
    write_json(output_dir / "geometry_definition_used.json", geometry.to_dict())
    write_json(output_dir / "geometry_source.json", {"geometry_path": str(geometry_path)})
    if injector_geometry is not None:
        write_json(output_dir / "injector_geometry_used.json", injector_geometry.to_dict())
        if injector_geometry_path is not None:
            write_json(output_dir / "injector_geometry_source.json", {"injector_geometry_path": str(injector_geometry_path)})
    if raw_cea_config is not None:
        write_json(output_dir / "cea_config_used.json", raw_cea_config)
    return {
        "output_dir": output_dir,
        "geometry": geometry,
        "injector_geometry": injector_geometry,
        "nominal_payload": nominal_payload,
        "corner_payload": corner_payload,
        "ballistics_payload": ballistics_payload,
        "payload": payload,
    }


def _export_thermal_run(
    study_config: Mapping[str, Any],
    structural_config: Mapping[str, Any],
    thermal_config: Mapping[str, Any],
    cea_config_path: str | None,
    output_root: Path,
    *,
    cea_config_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    structural_dependency = _export_structural_run(
        study_config,
        structural_config,
        cea_config_path,
        output_root,
        cea_config_override=cea_config_override,
    )
    output_dir = ensure_directory(output_root / THERMAL_DIRNAME)
    geometry = structural_dependency["geometry"]
    injector_geometry = structural_dependency["injector_geometry"]
    nominal_payload = structural_dependency["nominal_payload"]
    corner_payload = structural_dependency["corner_payload"]
    ballistics_payload = structural_dependency["ballistics_payload"]
    structural_result = structural_dependency["payload"]["result"]
    payload = run_thermal_sizing_workflow(
        study_config,
        thermal_config,
        str(output_dir),
        geometry=geometry,
        structural_result=structural_result,
        nominal_payload=nominal_payload,
        injector_geometry=injector_geometry,
        corner_payload=corner_payload,
        ballistics_payload=ballistics_payload,
    )
    write_json(output_dir / "design_config_used.json", study_config)
    write_json(output_dir / "structural_settings_used.json", structural_config)
    write_json(output_dir / "thermal_settings_used.json", thermal_config)
    write_json(output_dir / "geometry_definition_used.json", geometry.to_dict())
    if injector_geometry is not None:
        write_json(output_dir / "injector_geometry_used.json", injector_geometry.to_dict())
    write_json(output_dir / "structural_sizing_used.json", structural_result.to_dict())
    return {
        "output_dir": output_dir,
        "structural_dependency": structural_dependency,
        "payload": payload,
    }


def _export_nozzle_offdesign_run(
    study_config: Mapping[str, Any],
    structural_config: Mapping[str, Any],
    thermal_config: Mapping[str, Any],
    nozzle_offdesign_config: Mapping[str, Any],
    cea_config_path: str | None,
    output_root: Path,
    *,
    cea_config_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    geometry, geometry_path = _resolve_nozzle_offdesign_geometry(
        study_config,
        cea_config_path,
        output_root,
        cea_config_override=cea_config_override,
    )
    injector_geometry, injector_geometry_path = _resolve_nozzle_offdesign_injector_geometry(
        study_config,
        geometry,
        cea_config_path,
        output_root,
        cea_config_override=cea_config_override,
    )
    raw_cea_config = _resolved_cea_config(cea_config_path, cea_config_override) if (cea_config_path or cea_config_override) else None
    nominal_payload = run_nominal_case(
        study_config,
        frozen_geometry=geometry,
        injector_geometry=injector_geometry,
        raw_cea_config=raw_cea_config,
    )

    need_corner_payload = (
        structural_config["load_source"] == "corner_case_envelope"
        or structural_config["include_corner_case_envelope"]
        or thermal_config["load_source"] == "corner_case_envelope"
        or thermal_config["include_corner_case_envelope"]
        or nozzle_offdesign_config["source_mode"] == "corner_case_envelope"
        or nozzle_offdesign_config["include_corner_case_envelope"]
    )
    corner_payload = None
    if need_corner_payload:
        corner_payload = run_corner_cases(
            study_config,
            frozen_geometry=geometry,
            injector_geometry=injector_geometry,
            raw_cea_config=raw_cea_config,
        )

    need_ballistics_payload = (
        structural_config["load_source"] == "peak_1d"
        or structural_config["include_internal_ballistics_peak_case"]
        or thermal_config["load_source"] == "transient_1d"
        or thermal_config["include_internal_ballistics_case"]
        or nozzle_offdesign_config["source_mode"] == "transient_1d"
        or nozzle_offdesign_config["include_internal_ballistics_case"]
    )
    ballistics_payload = None
    if need_ballistics_payload:
        ballistics_payload = run_internal_ballistics_case(
            study_config,
            geometry,
            cea_data={"raw_config": raw_cea_config} if raw_cea_config is not None else None,
            injector_geometry=injector_geometry,
        )

    structural_output_dir = ensure_directory(output_root / STRUCTURAL_DIRNAME)
    structural_payload = run_structural_sizing_workflow(
        study_config,
        structural_config,
        str(structural_output_dir),
        geometry=geometry,
        nominal_payload=nominal_payload,
        injector_geometry=injector_geometry,
        corner_payload=corner_payload,
        ballistics_payload=ballistics_payload,
    )
    write_json(structural_output_dir / "design_config_used.json", study_config)
    write_json(structural_output_dir / "structural_settings_used.json", structural_config)
    write_json(structural_output_dir / "geometry_definition_used.json", geometry.to_dict())
    write_json(structural_output_dir / "geometry_source.json", {"geometry_path": str(geometry_path)})
    if injector_geometry is not None:
        write_json(structural_output_dir / "injector_geometry_used.json", injector_geometry.to_dict())
        if injector_geometry_path is not None:
            write_json(structural_output_dir / "injector_geometry_source.json", {"injector_geometry_path": str(injector_geometry_path)})
    if raw_cea_config is not None:
        write_json(structural_output_dir / "cea_config_used.json", raw_cea_config)

    thermal_output_dir = ensure_directory(output_root / THERMAL_DIRNAME)
    thermal_payload = run_thermal_sizing_workflow(
        study_config,
        thermal_config,
        str(thermal_output_dir),
        geometry=geometry,
        structural_result=structural_payload["result"],
        nominal_payload=nominal_payload,
        injector_geometry=injector_geometry,
        corner_payload=corner_payload,
        ballistics_payload=ballistics_payload,
    )
    write_json(thermal_output_dir / "design_config_used.json", study_config)
    write_json(thermal_output_dir / "structural_settings_used.json", structural_config)
    write_json(thermal_output_dir / "thermal_settings_used.json", thermal_config)
    write_json(thermal_output_dir / "geometry_definition_used.json", geometry.to_dict())
    if injector_geometry is not None:
        write_json(thermal_output_dir / "injector_geometry_used.json", injector_geometry.to_dict())
    write_json(thermal_output_dir / "structural_sizing_used.json", structural_payload["result"].to_dict())
    if raw_cea_config is not None:
        write_json(thermal_output_dir / "cea_config_used.json", raw_cea_config)

    nozzle_output_dir = ensure_directory(output_root / NOZZLE_OFFDESIGN_DIRNAME)
    nozzle_payload = run_nozzle_offdesign_workflow(
        study_config,
        nozzle_offdesign_config,
        str(nozzle_output_dir),
        geometry=geometry,
        nominal_payload=nominal_payload,
        structural_result=structural_payload["result"],
        thermal_result=thermal_payload["result"],
        corner_payload=corner_payload,
        ballistics_payload=ballistics_payload,
    )
    write_json(nozzle_output_dir / "design_config_used.json", study_config)
    write_json(nozzle_output_dir / "structural_settings_used.json", structural_config)
    write_json(nozzle_output_dir / "thermal_settings_used.json", thermal_config)
    write_json(nozzle_output_dir / "nozzle_offdesign_settings_used.json", nozzle_offdesign_config)
    write_json(nozzle_output_dir / "geometry_definition_used.json", geometry.to_dict())
    if injector_geometry is not None:
        write_json(nozzle_output_dir / "injector_geometry_used.json", injector_geometry.to_dict())
    write_json(nozzle_output_dir / "structural_sizing_used.json", structural_payload["result"].to_dict())
    write_json(nozzle_output_dir / "thermal_sizing_used.json", thermal_payload["result"].to_dict())
    if raw_cea_config is not None:
        write_json(nozzle_output_dir / "cea_config_used.json", raw_cea_config)
    return {
        "output_dir": nozzle_output_dir,
        "geometry": geometry,
        "injector_geometry": injector_geometry,
        "nominal_payload": nominal_payload,
        "corner_payload": corner_payload,
        "ballistics_payload": ballistics_payload,
        "structural_payload": structural_payload,
        "thermal_payload": thermal_payload,
        "payload": nozzle_payload,
    }


def _export_cfd_run(
    study_config: Mapping[str, Any],
    structural_config: Mapping[str, Any],
    thermal_config: Mapping[str, Any],
    nozzle_offdesign_config: Mapping[str, Any],
    cfd_config: Mapping[str, Any],
    cfd_mode: str,
    cea_config_path: str | None,
    output_root: Path,
    *,
    cea_config_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    geometry, geometry_path = _resolve_cfd_geometry(
        study_config,
        cea_config_path,
        output_root,
        cea_config_override=cea_config_override,
    )
    injector_geometry, injector_geometry_path = _resolve_cfd_injector_geometry(
        study_config,
        geometry,
        cea_config_path,
        output_root,
        cea_config_override=cea_config_override,
    )
    raw_cea_config = _resolved_cea_config(cea_config_path, cea_config_override) if (cea_config_path or cea_config_override) else None
    nominal_payload = run_nominal_case(
        study_config,
        frozen_geometry=geometry,
        injector_geometry=injector_geometry,
        raw_cea_config=raw_cea_config,
    )

    need_corner_payload = (
        structural_config["load_source"] == "corner_case_envelope"
        or structural_config["include_corner_case_envelope"]
        or thermal_config["load_source"] == "corner_case_envelope"
        or thermal_config["include_corner_case_envelope"]
        or nozzle_offdesign_config["source_mode"] == "corner_case_envelope"
        or nozzle_offdesign_config["include_corner_case_envelope"]
        or cfd_config["cfd_case_source"] == "corner_case_envelope"
        or cfd_config["include_corner_case_envelope"]
    )
    corner_payload = None
    if need_corner_payload:
        corner_payload = run_corner_cases(
            study_config,
            frozen_geometry=geometry,
            injector_geometry=injector_geometry,
            raw_cea_config=raw_cea_config,
        )

    need_ballistics_payload = (
        structural_config["load_source"] == "peak_1d"
        or structural_config["include_internal_ballistics_peak_case"]
        or thermal_config["load_source"] == "transient_1d"
        or thermal_config["include_internal_ballistics_case"]
        or nozzle_offdesign_config["source_mode"] == "transient_1d"
        or nozzle_offdesign_config["include_internal_ballistics_case"]
        or cfd_config["include_internal_ballistics_case"]
    )
    ballistics_payload = None
    if need_ballistics_payload:
        ballistics_payload = run_internal_ballistics_case(
            study_config,
            geometry,
            cea_data={"raw_config": raw_cea_config} if raw_cea_config is not None else None,
            injector_geometry=injector_geometry,
        )

    structural_output_dir = ensure_directory(output_root / STRUCTURAL_DIRNAME)
    structural_payload = run_structural_sizing_workflow(
        study_config,
        structural_config,
        str(structural_output_dir),
        geometry=geometry,
        nominal_payload=nominal_payload,
        injector_geometry=injector_geometry,
        corner_payload=corner_payload,
        ballistics_payload=ballistics_payload,
    )
    write_json(structural_output_dir / "design_config_used.json", study_config)
    write_json(structural_output_dir / "structural_settings_used.json", structural_config)
    write_json(structural_output_dir / "geometry_definition_used.json", geometry.to_dict())
    write_json(structural_output_dir / "geometry_source.json", {"geometry_path": str(geometry_path)})
    if injector_geometry is not None:
        write_json(structural_output_dir / "injector_geometry_used.json", injector_geometry.to_dict())
        if injector_geometry_path is not None:
            write_json(structural_output_dir / "injector_geometry_source.json", {"injector_geometry_path": str(injector_geometry_path)})
    if raw_cea_config is not None:
        write_json(structural_output_dir / "cea_config_used.json", raw_cea_config)

    thermal_output_dir = ensure_directory(output_root / THERMAL_DIRNAME)
    thermal_payload = run_thermal_sizing_workflow(
        study_config,
        thermal_config,
        str(thermal_output_dir),
        geometry=geometry,
        structural_result=structural_payload["result"],
        nominal_payload=nominal_payload,
        injector_geometry=injector_geometry,
        corner_payload=corner_payload,
        ballistics_payload=ballistics_payload,
    )
    write_json(thermal_output_dir / "design_config_used.json", study_config)
    write_json(thermal_output_dir / "structural_settings_used.json", structural_config)
    write_json(thermal_output_dir / "thermal_settings_used.json", thermal_config)
    write_json(thermal_output_dir / "geometry_definition_used.json", geometry.to_dict())
    if injector_geometry is not None:
        write_json(thermal_output_dir / "injector_geometry_used.json", injector_geometry.to_dict())
    write_json(thermal_output_dir / "structural_sizing_used.json", structural_payload["result"].to_dict())
    if raw_cea_config is not None:
        write_json(thermal_output_dir / "cea_config_used.json", raw_cea_config)

    nozzle_output_dir = ensure_directory(output_root / NOZZLE_OFFDESIGN_DIRNAME)
    nozzle_payload = run_nozzle_offdesign_workflow(
        study_config,
        nozzle_offdesign_config,
        str(nozzle_output_dir),
        geometry=geometry,
        nominal_payload=nominal_payload,
        structural_result=structural_payload["result"],
        thermal_result=thermal_payload["result"],
        corner_payload=corner_payload,
        ballistics_payload=ballistics_payload,
    )
    write_json(nozzle_output_dir / "design_config_used.json", study_config)
    write_json(nozzle_output_dir / "structural_settings_used.json", structural_config)
    write_json(nozzle_output_dir / "thermal_settings_used.json", thermal_config)
    write_json(nozzle_output_dir / "nozzle_offdesign_settings_used.json", nozzle_offdesign_config)
    write_json(nozzle_output_dir / "geometry_definition_used.json", geometry.to_dict())
    if injector_geometry is not None:
        write_json(nozzle_output_dir / "injector_geometry_used.json", injector_geometry.to_dict())
    write_json(nozzle_output_dir / "structural_sizing_used.json", structural_payload["result"].to_dict())
    write_json(nozzle_output_dir / "thermal_sizing_used.json", thermal_payload["result"].to_dict())
    if raw_cea_config is not None:
        write_json(nozzle_output_dir / "cea_config_used.json", raw_cea_config)

    cfd_output_dir = ensure_directory(output_root / CFD_DIRNAME)
    cfd_payload = run_cfd_workflow(
        study_config,
        cfd_config,
        str(cfd_output_dir),
        mode=cfd_mode,
        geometry=geometry,
        nominal_payload=nominal_payload,
        injector_geometry=injector_geometry,
        structural_result=structural_payload["result"],
        thermal_result=thermal_payload["result"],
        nozzle_result=nozzle_payload["result"],
        corner_payload=corner_payload,
        ballistics_payload=ballistics_payload,
    )
    write_json(cfd_output_dir / "design_config_used.json", study_config)
    write_json(cfd_output_dir / "structural_settings_used.json", structural_config)
    write_json(cfd_output_dir / "thermal_settings_used.json", thermal_config)
    write_json(cfd_output_dir / "nozzle_offdesign_settings_used.json", nozzle_offdesign_config)
    write_json(cfd_output_dir / "cfd_settings_used.json", cfd_config)
    write_json(cfd_output_dir / "geometry_definition_used.json", geometry.to_dict())
    if injector_geometry is not None:
        write_json(cfd_output_dir / "injector_geometry_used.json", injector_geometry.to_dict())
    write_json(cfd_output_dir / "structural_sizing_used.json", structural_payload["result"].to_dict())
    write_json(cfd_output_dir / "thermal_sizing_used.json", thermal_payload["result"].to_dict())
    write_json(cfd_output_dir / "nozzle_offdesign_used.json", nozzle_payload["result"].to_dict())
    if raw_cea_config is not None:
        write_json(cfd_output_dir / "cea_config_used.json", raw_cea_config)
    return {
        "output_dir": cfd_output_dir,
        "geometry": geometry,
        "injector_geometry": injector_geometry,
        "nominal_payload": nominal_payload,
        "corner_payload": corner_payload,
        "ballistics_payload": ballistics_payload,
        "structural_payload": structural_payload,
        "thermal_payload": thermal_payload,
        "nozzle_payload": nozzle_payload,
        "payload": cfd_payload,
    }


def _export_testing_run(
    study_config: Mapping[str, Any],
    structural_config: Mapping[str, Any],
    thermal_config: Mapping[str, Any],
    nozzle_offdesign_config: Mapping[str, Any],
    cfd_config: Mapping[str, Any],
    testing_config: Mapping[str, Any],
    cea_config_path: str | None,
    output_root: Path,
    *,
    cea_config_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    raw_cea_config = _resolved_cea_config(cea_config_path, cea_config_override) if (cea_config_path or cea_config_override) else None
    use_cfd_context = bool(testing_config.get("include_cfd_context", True)) or bool(testing_config.get("require_cfd_before_fullscale", False))
    if use_cfd_context:
        dependency = _export_cfd_run(
            study_config,
            structural_config,
            thermal_config,
            nozzle_offdesign_config,
            cfd_config,
            "cfd_plan",
            cea_config_path,
            output_root,
            cea_config_override=cea_config_override,
        )
        geometry = dependency["geometry"]
        injector_geometry = dependency["injector_geometry"]
        nominal_payload = dependency["nominal_payload"]
        ballistics_payload = dependency["ballistics_payload"]
        structural_payload = dependency["structural_payload"]
        thermal_payload = dependency["thermal_payload"]
        nozzle_payload = dependency["nozzle_payload"]
        cfd_payload = dependency["payload"]
    else:
        dependency = _export_nozzle_offdesign_run(
            study_config,
            structural_config,
            thermal_config,
            nozzle_offdesign_config,
            cea_config_path,
            output_root,
            cea_config_override=cea_config_override,
        )
        geometry = dependency["geometry"]
        injector_geometry = dependency["injector_geometry"]
        nominal_payload = dependency["nominal_payload"]
        ballistics_payload = dependency["ballistics_payload"]
        structural_payload = dependency["structural_payload"]
        thermal_payload = dependency["thermal_payload"]
        nozzle_payload = dependency["payload"]
        cfd_payload = None

    if ballistics_payload is None and (
        bool(testing_config.get("include_internal_ballistics_case", True))
        or str(testing_config.get("model_vs_test_source", "0d")).lower() in {"1d", "transient_1d"}
    ):
        ballistics_payload = run_internal_ballistics_case(
            study_config,
            geometry,
            cea_data={"raw_config": raw_cea_config} if raw_cea_config is not None else None,
            injector_geometry=injector_geometry,
        )

    output_dir = ensure_directory(output_root / TESTING_DIRNAME)
    payload = run_testing_workflow(
        dict(study_config),
        testing_config,
        str(output_dir),
        geometry=geometry,
        nominal_payload=nominal_payload,
        injector_geometry=injector_geometry,
        structural_result=structural_payload["result"],
        thermal_result=thermal_payload["result"],
        nozzle_result=nozzle_payload["result"],
        cfd_payload=cfd_payload,
        ballistics_payload=ballistics_payload,
    )
    write_json(output_dir / "design_config_used.json", study_config)
    write_json(output_dir / "structural_settings_used.json", structural_config)
    write_json(output_dir / "thermal_settings_used.json", thermal_config)
    write_json(output_dir / "nozzle_offdesign_settings_used.json", nozzle_offdesign_config)
    write_json(output_dir / "testing_settings_used.json", testing_config)
    write_json(output_dir / "geometry_definition_used.json", geometry.to_dict())
    if injector_geometry is not None:
        write_json(output_dir / "injector_geometry_used.json", injector_geometry.to_dict())
    write_json(output_dir / "structural_sizing_used.json", structural_payload["result"].to_dict())
    write_json(output_dir / "thermal_sizing_used.json", thermal_payload["result"].to_dict())
    write_json(output_dir / "nozzle_offdesign_used.json", nozzle_payload["result"].to_dict())
    if cfd_payload is not None:
        write_json(output_dir / "cfd_campaign_used.json", cfd_payload["plan"].to_dict())
    return {
        "output_dir": output_dir,
        "dependency": dependency,
        "payload": payload,
    }


