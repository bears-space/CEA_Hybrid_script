"""HTTP server for the workflow dashboard."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import logging
import threading
import time
import traceback
from copy import deepcopy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

from project_data import load_project_defaults
from src.cfd import merge_cfd_config
from src.config import (
    build_design_config,
    normalize_cfd_config,
    normalize_hydraulic_validation_config,
    normalize_nozzle_offdesign_config,
    normalize_structural_config,
    normalize_testing_config,
    normalize_thermal_config,
)
from src.hydraulic_validation import merge_hydraulic_validation_config
from src.io_utils import deep_merge, load_json
from src.nozzle_offdesign import merge_nozzle_offdesign_config
from src.structural import merge_structural_config
from src.testing import merge_testing_config
from src.thermal import merge_thermal_config
from src.logging_utils import configure_logging
from src.ui.workflow_map import workflow_map_payload
from src.ui.run_metadata import group_artifacts_by_section
from src.workflows import mode_definitions_payload, run_workflow, summary_lines
from src.workflows.modes import RUN_ALL_SEQUENCE

LOGGER = logging.getLogger(__name__)
HOST = "127.0.0.1"
PORT = 8000
ROOT_DIR = Path(__file__).resolve().parents[2]
UI_DIR = ROOT_DIR / "ui"
INPUT_DIR = ROOT_DIR / "input"
OUTPUT_DIR = ROOT_DIR / "output"
MAX_LOG_ENTRIES = 400
SECTION_DISPLAY_ORDER = [
    "thermochemistry",
    "performance",
    "analysis",
    "geometry",
    "internal_ballistics",
    "injector_design",
    "hydraulic_validation",
    "structural",
    "thermal",
    "nozzle_offdesign",
    "cfd",
    "testing",
]
SECTION_PRIMARY_STEP = {
    "thermochemistry": "cea",
    "performance": "nominal",
    "analysis": "corners",
    "geometry": "geometry",
    "internal_ballistics": "internal_ballistics",
    "injector_design": "injector_design",
    "hydraulic_validation": "hydraulic_predict",
    "structural": "structural_size",
    "thermal": "thermal_size",
    "nozzle_offdesign": "nozzle_offdesign",
    "cfd": "cfd_plan",
    "testing": "test_readiness",
}
CONFIG_STEP_KEYS = {
    "design_config": "design_config",
    "cea_config": "cea_config",
    "hydraulic_config": "hydraulic_validation_config",
    "structural_config": "structural_config",
    "thermal_config": "thermal_config",
    "nozzle_config": "nozzle_offdesign_config",
    "cfd_config": "cfd_config",
    "testing_config": "testing_config",
}
STEP_ARTIFACT_PREFIXES = {
    "cea": ("thermochemistry/",),
    "nominal": ("performance/",),
    "oat": ("analysis/sensitivity/",),
    "corners": ("analysis/corners/",),
    "geometry": ("geometry/",),
    "internal_ballistics": ("internal_ballistics/",),
    "injector_design": ("injector_design/",),
    "hydraulic_predict": ("hydraulic_validation/",),
    "hydraulic_calibrate": ("hydraulic_validation/",),
    "hydraulic_compare": ("hydraulic_validation/",),
    "structural_size": ("structural/",),
    "thermal_size": ("thermal/",),
    "nozzle_offdesign": ("nozzle_offdesign/",),
    "cfd_plan": ("cfd/",),
    "cfd_export_cases": ("cfd/",),
    "cfd_ingest_results": ("cfd/",),
    "cfd_apply_corrections": ("cfd/",),
    "test_plan": ("testing/",),
    "test_define_articles": ("testing/",),
    "test_ingest_data": ("testing/",),
    "test_compare_model": ("testing/",),
    "test_calibrate_hotfire": ("testing/",),
    "test_readiness": ("testing/",),
}
STEP_SECTION_METRIC_SOURCE = {
    "thermal_size": "thermal",
    "nozzle_offdesign": "nozzle_offdesign",
    "cfd_plan": "cfd",
    "cfd_export_cases": "cfd",
    "cfd_ingest_results": "cfd",
    "cfd_apply_corrections": "cfd",
    "test_plan": "testing",
    "test_define_articles": "testing",
    "test_ingest_data": "testing",
    "test_compare_model": "testing",
    "test_calibrate_hotfire": "testing",
    "test_readiness": "testing",
}
CSV_FIELD_SIZE_LIMIT = 10_000_000
VARIABLE_DEFAULT_PATHS: dict[str, tuple[str, ...]] = {
    "target_thrust_n": ("cea_config", "target_thrust_n"),
    "target_pc_bar": ("design_config", "nominal", "performance", "pc_bar"),
    "burn_time_s": ("design_config", "nominal", "blowdown", "simulation", "burn_time_s"),
    "of_sweep_range": ("cea_config", "sweeps", "of"),
    "abs_volume_fraction_range": ("cea_config", "sweeps", "abs_volume_fractions"),
    "ae_at_sweep_range": ("cea_config", "sweeps", "ae_at"),
    "rig_dataset_path": ("testing_config", "dataset_path"),
    "calibration_mode": ("hydraulic_validation_config", "calibration_mode"),
    "saved_calibration_package": ("hydraulic_validation_config", "calibration_package_path"),
    "minimum_wall_thickness_m": ("structural_config", "design_policy", "minimum_wall_thickness_m"),
    "structural_safety_factor": ("structural_config", "design_policy", "yield_safety_factor"),
    "thermal_model_name": ("thermal_config", "design_policy", "wall_model_type"),
    "heat_flux_margin_factor": ("thermal_config", "design_policy", "throat_htc_multiplier"),
    "ambient_case_altitudes_m": ("nozzle_offdesign_config", "ambient_cases"),
    "include_vacuum_case": ("nozzle_offdesign_config", "ambient_sweep", "include_vacuum_case"),
    "separation_risk_threshold": ("nozzle_offdesign_config", "separation_thresholds", "moderate_risk_ratio"),
    "target_case_count": ("cfd_config", "target_case_count"),
    "case_export_format": ("cfd_config", "preferred_export_formats"),
    "correction_ingest_enabled": ("cfd_config", "correction_ingest_enabled"),
    "stage_sequence": ("testing_config", "stage_order"),
    "readiness_pass_threshold": ("testing_config", "progression_thresholds"),
    "test_dataset_root": ("testing_config", "dataset_path"),
}
VARIABLE_ALIASES: dict[str, tuple[str, ...]] = {
    "c_star_m_s": ("cstar_mps",),
    "gamma_exit": ("gamma_e",),
    "molecular_weight_exit": ("mw_e",),
    "combustion_temperature_k": ("tc_k",),
    "target_pc_bar": ("pc_bar",),
    "of_ratio_avg": ("of_avg",),
    "of_ratio_corner": ("of_avg",),
    "total_impulse_ns": ("impulse_total_ns",),
    "burn_time_effective_s": ("burn_time_actual_s",),
    "parameter_name": ("parameter",),
    "response_metric": ("metric", "target_metric"),
    "delta_fraction": ("delta_rel", "delta_fraction", "sensitivity_value", "normalized_sensitivity"),
    "sensitivity_rank": ("rank",),
    "corner_name": ("case_name",),
    "matched_altitude_m": ("matched_altitude_m", "altitude_m"),
    "constraints_pass": ("constraints_pass", "constraints_all_pass"),
    "time_s": ("time_s", "t_s"),
    "pc_bar": ("pc_bar", "pc_avg_bar"),
    "thrust_n": ("thrust_n", "thrust_avg_n"),
    "mdot_total_kg_s": ("mdot_total_kg_s", "total_mass_flow_kg_s"),
    "port_radius_m": ("port_radius_m", "port_radius"),
    "injector_orifice_count": ("orifice_count", "hole_count"),
    "injector_orifice_diameter_m": ("orifice_diameter_m", "orifice_diameter", "hole_diameter_m"),
    "injector_cd": ("cd", "injector_cd"),
    "injector_dp_bar": ("injector_dp_bar", "injector_delta_p_bar"),
    "oxidizer_mass_flow_kg_s": ("oxidizer_mass_flow_kg_s", "mass_flow_kg_s"),
    "line_loss_factor": ("line_loss_factor", "feed_loss_factor"),
    "calibration_quality_flag": ("calibration_quality_flag", "calibration_pass_flag"),
    "minimum_margin_of_safety": ("minimum_margin_of_safety", "min_margin_of_safety"),
    "governing_region_name": ("governing_region_name", "governing_region"),
    "average_thrust_n": ("average_thrust_n",),
    "average_isp_s": ("average_isp_s",),
    "separation_risk_level": ("separation_risk_level", "risk_level"),
    "recommended_usage_mode": ("recommended_usage_mode",),
    "target_name": ("target_name", "recommended_next_target_name"),
    "boundary_condition_set": ("boundary_condition_set", "boundary_conditions"),
    "ambient_pressure_pa": ("ambient_pressure_pa",),
    "pressure_loss_factor": ("pressure_loss_factor",),
    "recommended_next_stage": ("recommended_next_stage", "recommended_next_test"),
    "blocking_gate_name": ("blocking_gate_name",),
    "evidence_gap_count": ("evidence_gap_count",),
    "agreement_flag": ("agreement_flag",),
    "burn_time_test_s": ("achieved_burn_time_s",),
    "fit_quality_score": ("fit_quality_score",),
}

JOB_LOCK = threading.Lock()
JOB_STATE: dict[str, Any] = {
    "job_id": 0,
    "status": "idle",
    "mode": None,
    "message": "Ready.",
    "started_at": None,
    "finished_at": None,
    "result": None,
    "error": None,
    "traceback": None,
    "thread": None,
    "logs": [],
}


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return load_json(path)


def _load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    return load_json(path)


def _first_existing_path(*paths: Path) -> Path | None:
    for path in paths:
        if path.exists() and path.is_file():
            return path
    return None


def _metric_card(label: str, value: Any, unit: str = "", *, emphasis: str = "neutral") -> dict[str, Any]:
    return {
        "label": label,
        "value": value,
        "unit": unit,
        "emphasis": emphasis,
    }


def _summary_items(summary: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not summary:
        return []
    items: list[dict[str, Any]] = []
    for key, value in summary.items():
        items.append(
            {
                "label": key.replace("_", " ").title(),
                "value": value,
            }
        )
    return items


def _latest_geometry_payload(root: Path) -> dict[str, Any] | None:
    geometry_path = _first_existing_path(
        root / "geometry" / "geometry_definition.json",
        root / "geometry" / "geometry_definition_used.json",
        root / "nozzle_offdesign" / "geometry_definition_used.json",
        root / "thermal" / "geometry_definition_used.json",
        root / "structural" / "geometry_definition_used.json",
    )
    if geometry_path is None:
        return None
    geometry = _load_json_if_exists(geometry_path)
    if not geometry:
        return None
    return {
        "source_path": geometry_path.relative_to(root).as_posix(),
        "chamber_id_m": geometry.get("chamber_id_m"),
        "chamber_inner_diameter_including_liner_m": geometry.get("chamber_inner_diameter_including_liner_m"),
        "chamber_outer_diameter_including_liner_m": geometry.get("chamber_outer_diameter_including_liner_m"),
        "chamber_inner_diameter_excluding_liner_m": geometry.get("chamber_inner_diameter_excluding_liner_m"),
        "chamber_outer_diameter_excluding_liner_m": geometry.get("chamber_outer_diameter_excluding_liner_m"),
        "fuel_inner_diameter_m": geometry.get("fuel_inner_diameter_m"),
        "fuel_outer_diameter_m": geometry.get("fuel_outer_diameter_m"),
        "throat_diameter_m": geometry.get("throat_diameter_m"),
        "nozzle_exit_diameter_m": geometry.get("nozzle_exit_diameter_m"),
        "total_chamber_length_m": geometry.get("total_chamber_length_m"),
        "inner_liner_thickness_m": geometry.get("inner_liner_thickness_m"),
        "injector_hole_count": geometry.get("injector_hole_count"),
        "injector_total_hole_area_m2": geometry.get("injector_total_hole_area_m2"),
        "injector_hole_diameter_m": geometry.get("injector_hole_diameter_m"),
        "converging_throat_half_angle_deg": geometry.get("converging_throat_half_angle_deg"),
        "diverging_throat_half_angle_deg": geometry.get("diverging_throat_half_angle_deg"),
        "throat_blend_radius_m": geometry.get("throat_blend_radius_m"),
        "converging_section_length_m": geometry.get("converging_section_length_m"),
        "converging_section_arc_length_m": geometry.get("converging_section_arc_length_m"),
        "converging_straight_length_m": geometry.get("converging_straight_length_m"),
        "converging_blend_arc_length_m": geometry.get("converging_blend_arc_length_m"),
        "nozzle_length_m": geometry.get("nozzle_length_m"),
        "nozzle_arc_length_m": geometry.get("nozzle_arc_length_m"),
        "nozzle_straight_length_m": geometry.get("nozzle_straight_length_m"),
        "nozzle_blend_arc_length_m": geometry.get("nozzle_blend_arc_length_m"),
        "nozzle_contour_style": geometry.get("nozzle_contour_style"),
        "nozzle_profile": dict(geometry.get("nozzle_profile") or {}),
        "grain_length_m": geometry.get("grain_length_m"),
        "prechamber_length_m": geometry.get("prechamber_length_m"),
        "postchamber_length_m": geometry.get("postchamber_length_m"),
        "port_radius_initial_m": geometry.get("port_radius_initial_m"),
        "injector_face_diameter_m": geometry.get("injector_face_diameter_m"),
        "geometry_valid": geometry.get("geometry_valid"),
        "notes": list(geometry.get("notes") or []),
    }


def _title_case_slug(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def _chart_groups(root: Path, manifest: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    sections = dict((manifest or {}).get("sections") or {})
    ordered_section_names = list(dict.fromkeys([*SECTION_DISPLAY_ORDER, *sections.keys()]))
    groups: list[dict[str, Any]] = []
    requested_mode = str((manifest or {}).get("requested_mode") or "")
    for section_name in ordered_section_names:
        manifest_path = sections.get(section_name)
        section_path = Path(manifest_path) if manifest_path else root / section_name
        if not section_path.exists() or not section_path.is_dir():
            continue
        svg_paths = sorted(section_path.glob("*.svg"))
        if not svg_paths:
            continue
        detail_step = (
            requested_mode
            if section_name == "analysis" and requested_mode in {"oat", "corners"}
            else SECTION_PRIMARY_STEP.get(section_name, section_name)
        )
        charts = [
            {
                "title": _title_case_slug(path.stem),
                "relative_path": path.relative_to(root).as_posix(),
            }
            for path in svg_paths
        ]
        groups.append(
            {
                "key": section_name,
                "title": _title_case_slug(section_name),
                "chart_count": len(charts),
                "detail_href": f"/simulation.html?step={detail_step}",
                "charts": charts,
            }
        )
    return groups


def _workflow_nodes_by_id() -> dict[str, dict[str, Any]]:
    return {node["id"]: dict(node) for node in workflow_map_payload()["nodes"]}


def _workflow_downstream() -> dict[str, list[dict[str, str]]]:
    nodes = _workflow_nodes_by_id()
    downstream: dict[str, list[dict[str, str]]] = {node_id: [] for node_id in nodes}
    for edge in workflow_map_payload()["edges"]:
        target = nodes.get(str(edge["to"]))
        if target is None:
            continue
        downstream.setdefault(str(edge["from"]), []).append(
            {
                "id": target["id"],
                "title": target["title"],
                "label": str(edge["label"]),
                "detail_href": str(target.get("detail_href") or f"/simulation.html?step={target['id']}"),
            }
        )
    return downstream


def _artifact_index_rows(root: Path) -> list[dict[str, Any]]:
    artifact_index_path = root / "artifact_index.csv"
    if not artifact_index_path.exists():
        return []
    with artifact_index_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return [dict(row) for row in csv.DictReader(csv_file)]


def _coerce_csv_value(value: str | None) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        numeric = float(text)
    except ValueError:
        return text
    if numeric.is_integer():
        return int(numeric)
    return numeric


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    csv.field_size_limit(CSV_FIELD_SIZE_LIMIT)
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        return [{key: _coerce_csv_value(value) for key, value in row.items()} for row in reader]


def _read_csv_table(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {"columns": [], "rows": []}
    csv.field_size_limit(CSV_FIELD_SIZE_LIMIT)
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        columns = list(reader.fieldnames or [])
        rows = [{key: _coerce_csv_value(value) for key, value in row.items()} for row in reader]
    return {"columns": columns, "rows": rows}


def _path_lookup(mapping: Mapping[str, Any] | None, path: tuple[str, ...]) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _variable_candidate_names(name: str) -> list[str]:
    return [name, *VARIABLE_ALIASES.get(name, ())]


def _search_json_values(payload: Any, candidates: set[str]) -> list[Any]:
    matches: list[Any] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if key in candidates:
                matches.append(value)
            matches.extend(_search_json_values(value, candidates))
    elif isinstance(payload, list):
        for item in payload:
            matches.extend(_search_json_values(item, candidates))
    return matches


def _json_artifacts_for_root(root: Path) -> list[tuple[str, Any]]:
    docs: list[tuple[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        if path.stat().st_size > 1_000_000:
            continue
        with path.open("r", encoding="utf-8-sig") as handle:
            try:
                docs.append((path.relative_to(root).as_posix(), json.load(handle)))
            except json.JSONDecodeError:
                continue
    return docs


def _csv_tables_for_root(root: Path) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.csv")):
        if not path.is_file() or path.name in {"artifact_index.csv", "all_outputs.csv"}:
            continue
        table = _read_csv_table(path)
        tables.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "columns": table["columns"],
                "rows": table["rows"],
            }
        )
    return tables


def _resolve_special_value(name: str, root: Path | None, json_docs: list[tuple[str, Any]]) -> tuple[Any, str | None]:
    if root is None:
        return None, None
    nominal_metrics = _load_json_if_exists(root / "performance" / "nominal_metrics.json") or {}
    nominal_metric_names = {
        "pc_avg_bar": "pc_avg_bar",
        "thrust_avg_n": "thrust_avg_n",
        "of_ratio_avg": "of_avg",
        "total_impulse_ns": "impulse_total_ns",
        "burn_time_effective_s": "burn_time_actual_s",
    }
    if name in nominal_metric_names and nominal_metrics.get(nominal_metric_names[name]) is not None:
        return nominal_metrics[nominal_metric_names[name]], "performance/nominal_metrics.json"
    if name == "material_yield_strength_pa":
        structural_settings = _load_json_if_exists(root / "structural" / "structural_settings_used.json") or {}
        if not structural_settings:
            structural_settings = _default_payload().get("structural_config") or {}
        if isinstance(structural_settings, Mapping):
            with contextlib.suppress(Exception):
                from src.structural.material_db import _base_material_catalog

                policy_data = dict(structural_settings.get("design_policy", {}))
                material_key = str(structural_settings.get("component_materials", {}).get("chamber_wall", "aluminum_6061_t6")).strip().lower()
                material = dict(structural_settings.get("custom_materials", {}).get(material_key) or _base_material_catalog().get(material_key) or {})
                allowable_basis = str(structural_settings.get("allowable_basis", "yield_based"))
                if allowable_basis == "ultimate_based":
                    allowable = float(material["ultimate_strength_pa"]) / float(policy_data.get("ultimate_safety_factor", 2.0))
                elif allowable_basis == "user_override" and material.get("allowable_stress_pa") is not None:
                    allowable = float(material["allowable_stress_pa"])
                else:
                    allowable = float(material["yield_strength_pa"]) / float(policy_data.get("yield_safety_factor", 1.5))
                source = "structural/structural_settings_used.json" if (root / "structural" / "structural_settings_used.json").exists() else "defaults"
                return allowable, source
    if name == "allowable_wall_temp_k":
        thermal_settings = _load_json_if_exists(root / "thermal" / "thermal_settings_used.json") or {}
        if not thermal_settings:
            thermal_settings = _default_payload().get("thermal_config") or {}
        if isinstance(thermal_settings, Mapping):
            with contextlib.suppress(Exception):
                from src.thermal.material_thermal_db import _base_material_catalog

                policy_data = dict(thermal_settings.get("design_policy", {}))
                material_key = str(thermal_settings.get("component_materials", {}).get("chamber_wall", "aluminum_6061_t6")).strip().lower()
                material = dict(thermal_settings.get("custom_materials", {}).get(material_key) or _base_material_catalog().get(material_key) or {})
                basis = material.get("max_service_temp_k")
                if str(policy_data.get("temperature_limit_basis", "max_service_temp")) == "softening_temp" and material.get("melt_or_softening_temp_k") is not None:
                    basis = material.get("melt_or_softening_temp_k")
                if basis is not None:
                    source = "thermal/thermal_settings_used.json" if (root / "thermal" / "thermal_settings_used.json").exists() else "defaults"
                    return max(float(basis) - float(policy_data.get("service_temp_margin_k", 40.0)), 1.0), source
    if name == "ambient_case_altitudes_m":
        data = _load_json_if_exists(root / "nozzle_offdesign" / "nozzle_offdesign_settings_used.json")
        if isinstance(data, Mapping):
            cases = list(data.get("ambient_cases") or [])
            altitudes = [case.get("altitude_m") for case in cases if isinstance(case, Mapping)]
            return altitudes, "nozzle_offdesign/nozzle_offdesign_settings_used.json"
    if name == "oxidizer_name":
        defaults = _default_payload().get("cea_config") or {}
        value = _path_lookup(defaults, ("species", "oxidizer"))
        if value is not None:
            return value, "defaults"
    if name == "fuel_name":
        defaults = _default_payload().get("cea_config") or {}
        fuel_main = _path_lookup(defaults, ("species", "fuel_main"))
        if fuel_main is not None:
            return fuel_main, "defaults"
    if name == "cea_chamber_pressure_pa":
        defaults = _default_payload().get("cea_config") or {}
        if _path_lookup(defaults, ("chamber_pressure_pa",)) is not None:
            return _path_lookup(defaults, ("chamber_pressure_pa",)), "defaults"
        pc_bar = _path_lookup(defaults, ("pc_bar",))
        if pc_bar is not None:
            return float(pc_bar) * 1.0e5, "defaults"
    if name == "target_case_count":
        defaults = _default_payload().get("cfd_config") or {}
        enabled_targets = list(defaults.get("enabled_targets") or [])
        if enabled_targets:
            return len(enabled_targets), "defaults"
    if name == "correction_ingest_enabled":
        defaults = _default_payload().get("cfd_config") or {}
        result_path = str(defaults.get("result_ingest_path") or "").strip()
        return bool(result_path), "defaults"
    if name == "blocking_gate_name":
        readiness = _load_json_if_exists(root / "testing" / "readiness_summary.json") or {}
        blockers = list(readiness.get("outstanding_blockers") or [])
        return (None if not blockers else blockers[0]), "testing/readiness_summary.json"
    if name == "evidence_gap_count":
        readiness = _load_json_if_exists(root / "testing" / "readiness_summary.json") or {}
        blockers = list(readiness.get("outstanding_blockers") or [])
        return len(blockers), "testing/readiness_summary.json"
    if name == "response_metric":
        for relative_path, payload in json_docs:
            if relative_path.endswith("geometry/geometry_context.json") and isinstance(payload, Mapping):
                metric = payload.get("sensitivity_driver_metric")
                if metric is not None:
                    return metric, relative_path
        return None, None
    if name == "stage_sequence":
        for relative_path, payload in json_docs:
            if relative_path.endswith("testing/test_campaign_plan.json") and isinstance(payload, Mapping):
                stage_order = payload.get("stage_order")
                if stage_order is not None:
                    return stage_order, relative_path
        return None, None
    if name == "peak_inner_wall_temp_k":
        table = _read_csv_table(root / "thermal" / "thermal_region_histories.csv")
        values = [row.get("inner_wall_temp_k") for row in table["rows"] if isinstance(row.get("inner_wall_temp_k"), (int, float))]
        if values:
            return max(values), "thermal/thermal_region_histories.csv"
    if name == "peak_heat_flux_w_m2":
        table = _read_csv_table(root / "thermal" / "thermal_region_histories.csv")
        values = [row.get("heat_flux_w_m2") for row in table["rows"] if isinstance(row.get("heat_flux_w_m2"), (int, float))]
        if values:
            return max(values), "thermal/thermal_region_histories.csv"
    if name == "sensitivity_rank":
        table = _read_csv_table(root / "analysis" / "sensitivity" / "ranking_impulse_total_ns.csv")
        rows = table["rows"]
        if rows:
            return list(range(1, len(rows) + 1)), "analysis/sensitivity/ranking_impulse_total_ns.csv"
    if name == "injector_dp_bar":
        data = _load_json_if_exists(root / "injector_design" / "injector_geometry.json") or {}
        if data.get("design_injector_delta_p_pa") is not None:
            return float(data["design_injector_delta_p_pa"]) / 1.0e5, "injector_design/injector_geometry.json"
    if name == "shell_thickness_m":
        data = _load_json_if_exists(root / "structural" / "structural_sizing.json") or {}
        value = _path_lookup(data, ("chamber_wall_result", "selected_thickness_m"))
        if value is not None:
            return value, "structural/structural_sizing.json"
    if name == "closure_thickness_m":
        data = _load_json_if_exists(root / "structural" / "structural_sizing.json") or {}
        forward = _path_lookup(data, ("forward_closure_result", "selected_thickness_m"))
        aft = _path_lookup(data, ("aft_closure_result", "selected_thickness_m"))
        if forward is not None or aft is not None:
            return {"forward_closure_m": forward, "aft_closure_m": aft}, "structural/structural_sizing.json"
    if name == "injector_plate_thickness_m":
        data = _load_json_if_exists(root / "structural" / "structural_sizing.json") or {}
        value = _path_lookup(data, ("injector_plate_result", "selected_thickness_m"))
        if value is not None:
            return value, "structural/structural_sizing.json"
    if name == "minimum_margin_of_safety":
        data = _load_json_if_exists(root / "structural" / "structural_sizing.json") or {}
        summary = data.get("summary_margins")
        if isinstance(summary, Mapping):
            numeric = [float(value) for value in summary.values() if isinstance(value, (int, float))]
            if numeric:
                return min(numeric), "structural/structural_sizing.json"
    if name == "hardware_configuration":
        data = _load_json_if_exists(root / "testing" / "test_articles.json") or {}
        articles = list(data.get("articles") or [])
        if articles:
            return [
                {
                    "article_id": article.get("article_id"),
                    "article_type": article.get("article_type"),
                    "injector_reference": article.get("injector_reference"),
                    "nozzle_reference": article.get("nozzle_reference"),
                }
                for article in articles
                if isinstance(article, Mapping)
            ], "testing/test_articles.json"
    if name == "instrumentation_channel_count":
        data = _load_json_if_exists(root / "testing" / "instrumentation_plans.json") or {}
        plans = list(data.get("instrumentation_plans") or [])
        if plans:
            return [
                {
                    "article_id": plan.get("article_id"),
                    "channel_count": len(list(plan.get("channels") or [])),
                }
                for plan in plans
                if isinstance(plan, Mapping)
            ], "testing/instrumentation_plans.json"
    if name == "acceptance_criteria":
        data = _load_json_if_exists(root / "testing" / "test_campaign_plan.json") or {}
        stages = list(data.get("stages") or [])
        if stages:
            return [
                {
                    "stage_name": stage.get("stage_name"),
                    "success_metrics": list(stage.get("success_metrics") or []),
                }
                for stage in stages
                if isinstance(stage, Mapping)
            ], "testing/test_campaign_plan.json"
    if name == "required_instrumentation_set":
        data = _load_json_if_exists(root / "testing" / "test_campaign_plan.json") or {}
        stages = list(data.get("stages") or [])
        if stages:
            return [
                {
                    "stage_name": stage.get("stage_name"),
                    "required_measurements": list(stage.get("required_measurements") or []),
                }
                for stage in stages
                if isinstance(stage, Mapping)
            ], "testing/test_campaign_plan.json"
    if name == "mesh_reference_id":
        geometry_dir = root / "cfd" / "geometry_packages"
        if geometry_dir.exists():
            return [path.stem for path in sorted(geometry_dir.glob("*.json"))], "cfd/geometry_packages"
    return None, None


def _resolve_variable_value(
    name: str,
    *,
    defaults: Mapping[str, Any] | None,
    root: Path | None,
    json_docs: list[tuple[str, Any]],
    csv_tables: list[dict[str, Any]],
) -> tuple[Any, str | None]:
    if defaults:
        default_path = VARIABLE_DEFAULT_PATHS.get(name)
        if default_path:
            default_value = _path_lookup(defaults, default_path)
            if default_value is not None:
                return default_value, "defaults"

    candidates = set(_variable_candidate_names(name))
    special_value, special_source = _resolve_special_value(name, root, json_docs)
    if special_source is not None or special_value is not None:
        return special_value, special_source

    for table in csv_tables:
        for candidate in candidates:
            if candidate not in table["columns"]:
                continue
            values = [row.get(candidate) for row in table["rows"]]
            if not values:
                continue
            if len(values) == 1:
                return values[0], table["relative_path"]
            return values, table["relative_path"]

    generated_json_docs = [
        (relative_path, payload)
        for relative_path, payload in json_docs
        if "config_used" not in relative_path and "settings_used" not in relative_path and "design_config_used" not in relative_path
    ]
    config_json_docs = [
        (relative_path, payload)
        for relative_path, payload in json_docs
        if relative_path not in {path for path, _ in generated_json_docs}
    ]

    for relative_path, payload in [*generated_json_docs, *config_json_docs]:
        matches = _search_json_values(payload, candidates)
        if not matches:
            continue
        if len(matches) == 1:
            return matches[0], relative_path
        return matches, relative_path

    return None, None


def _resolved_io_items(
    items: list[dict[str, Any]],
    *,
    defaults: Mapping[str, Any] | None,
    root: Path | None,
    json_docs: list[tuple[str, Any]],
    csv_tables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for item in items:
        value, source = _resolve_variable_value(
            str(item.get("name") or ""),
            defaults=defaults,
            root=root,
            json_docs=json_docs,
            csv_tables=csv_tables,
        )
        resolved.append({**item, "value": value, "value_source": source})
    return resolved


def _numeric_series_chart(
    title: str,
    rows: list[dict[str, Any]],
    *,
    x_key: str,
    y_key: str,
    series_key: str | None = None,
    kind: str = "line",
    x_label: str | None = None,
    y_label: str | None = None,
) -> dict[str, Any] | None:
    grouped: dict[str, list[dict[str, float]]] = {}
    for row in rows:
        x_value = row.get(x_key)
        y_value = row.get(y_key)
        if not isinstance(x_value, (int, float)) or not isinstance(y_value, (int, float)):
            continue
        if not (float("-inf") < float(x_value) < float("inf") and float("-inf") < float(y_value) < float("inf")):
            continue
        series_name = str(row.get(series_key) or "Series") if series_key else "Series"
        grouped.setdefault(series_name, []).append({"x": float(x_value), "y": float(y_value)})
    if not grouped:
        return None
    series = []
    for name, points in grouped.items():
        series.append({"name": name, "points": sorted(points, key=lambda point: point["x"])})
    return {
        "title": title,
        "kind": kind,
        "x_label": x_label or _title_case_slug(x_key),
        "y_label": y_label or _title_case_slug(y_key),
        "series": series,
    }


def _category_bar_chart(
    title: str,
    rows: list[dict[str, Any]],
    *,
    category_key: str,
    value_key: str,
    x_label: str | None = None,
    y_label: str | None = None,
) -> dict[str, Any] | None:
    bars = []
    for row in rows:
        category = row.get(category_key)
        value = row.get(value_key)
        if category in {None, ""} or not isinstance(value, (int, float)):
            continue
        bars.append({"label": str(category), "value": float(value)})
    if not bars:
        return None
    return {
        "title": title,
        "kind": "bar",
        "x_label": x_label or _title_case_slug(category_key),
        "y_label": y_label or _title_case_slug(value_key),
        "bars": bars,
    }


def _count_bar_chart(title: str, rows: list[dict[str, Any]], *, category_key: str) -> dict[str, Any] | None:
    counts: dict[str, int] = {}
    for row in rows:
        category = row.get(category_key)
        if category in {None, ""}:
            continue
        counts[str(category)] = counts.get(str(category), 0) + 1
    if not counts:
        return None
    return {
        "title": title,
        "kind": "bar",
        "x_label": _title_case_slug(category_key),
        "y_label": "Count",
        "bars": [{"label": label, "value": float(value)} for label, value in counts.items()],
    }


def _section_downloads(root: Path, section: str) -> list[dict[str, Any]]:
    section_path = root / section
    if not section_path.exists() or not section_path.is_dir():
        return []
    downloads = []
    for path in sorted(section_path.rglob("*")):
        if not path.is_file():
            continue
        downloads.append(
            {
                "label": path.name,
                "relative_path": path.relative_to(root).as_posix(),
            }
        )
    return downloads


def _step_artifacts(root: Path, step: str) -> list[dict[str, Any]]:
    prefixes = STEP_ARTIFACT_PREFIXES.get(step, ())
    if not prefixes:
        return []
    rows = _artifact_index_rows(root)
    matched = []
    for row in rows:
        relative_path = str(row.get("relative_path") or "")
        if any(relative_path.startswith(prefix) for prefix in prefixes):
            matched.append(row)
    if matched:
        return matched
    artifacts = []
    for prefix in prefixes:
        base_path = root / prefix.rstrip("/")
        if not base_path.exists():
            continue
        for path in sorted(base_path.rglob("*")):
            if not path.is_file():
                continue
            artifacts.append(
                {
                    "section": prefix.rstrip("/").split("/")[0],
                    "relative_path": path.relative_to(root).as_posix(),
                    "filename": path.name,
                    "extension": path.suffix,
                    "size_bytes": path.stat().st_size,
                }
            )
    return artifacts


def _step_tables(root: Path, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tables = []
    for artifact in artifacts:
        relative_path = str(artifact.get("relative_path") or "")
        if not relative_path.endswith(".csv"):
            continue
        table = _read_csv_table(root / relative_path)
        tables.append(
            {
                "key": relative_path,
                "title": _title_case_slug(Path(relative_path).stem),
                "relative_path": relative_path,
                "columns": table["columns"],
                "rows": table["rows"],
            }
        )
    return tables


def _json_artifact_previews(root: Path, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    previews = []
    for artifact in artifacts:
        relative_path = str(artifact.get("relative_path") or "")
        path = root / relative_path
        if not relative_path.endswith(".json") or not path.exists() or path.stat().st_size > 1_000_000:
            continue
        with path.open("r", encoding="utf-8-sig") as handle:
            try:
                content = json.load(handle)
            except json.JSONDecodeError:
                continue
        previews.append(
            {
                "title": _title_case_slug(Path(relative_path).stem),
                "relative_path": relative_path,
                "content": content,
            }
        )
    return previews


def _svg_exports(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exports = []
    for artifact in artifacts:
        relative_path = str(artifact.get("relative_path") or "")
        if not relative_path.endswith(".svg"):
            continue
        exports.append(
            {
                "title": _title_case_slug(Path(relative_path).stem),
                "relative_path": relative_path,
            }
        )
    return exports


def _step_chart_hints(step: str, tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    table_keys = {table["key"] for table in tables}

    def has(key: str) -> bool:
        return key in table_keys

    hints: list[dict[str, Any]] = []
    if step == "thermal_size" and has("thermal/thermal_region_histories.csv"):
        for title, y_key, y_label in [
            ("Heat Flux by Region", "heat_flux_w_m2", "Heat Flux [W/m^2]"),
            ("Inner Wall Temperature by Region", "inner_wall_temp_k", "Inner Wall Temperature [K]"),
            ("Outer Wall Temperature by Region", "outer_wall_temp_k", "Outer Wall Temperature [K]"),
        ]:
            hints.append(
                {
                    "title": title,
                    "kind": "line",
                    "table_key": "thermal/thermal_region_histories.csv",
                    "x_key": "time_s",
                    "y_key": y_key,
                    "series_key": "region",
                    "x_label": "Time [s]",
                    "y_label": y_label,
                }
            )
    elif step == "nozzle_offdesign":
        if has("nozzle_offdesign/nozzle_operating_points.csv"):
            hints.extend(
                [
                    {
                        "title": "Average Thrust by Environment",
                        "kind": "bar",
                        "table_key": "nozzle_offdesign/nozzle_operating_points.csv",
                        "category_key": "case_name",
                        "value_key": "average_thrust_n",
                        "x_label": "Environment",
                        "y_label": "Average Thrust [N]",
                    },
                    {
                        "title": "Average Isp by Environment",
                        "kind": "bar",
                        "table_key": "nozzle_offdesign/nozzle_operating_points.csv",
                        "category_key": "case_name",
                        "value_key": "average_isp_s",
                        "x_label": "Environment",
                        "y_label": "Average Isp [s]",
                    },
                ]
            )
        if has("nozzle_offdesign/nozzle_transient_offdesign.csv"):
            hints.append(
                {
                    "title": "Transient Thrust by Environment",
                    "kind": "line",
                    "table_key": "nozzle_offdesign/nozzle_transient_offdesign.csv",
                    "x_key": "time_s",
                    "y_key": "thrust_n",
                    "series_key": "case_name",
                    "x_label": "Time [s]",
                    "y_label": "Thrust [N]",
                }
            )
    elif step in {"cfd_plan", "cfd_export_cases", "cfd_ingest_results", "cfd_apply_corrections"}:
        if has("cfd/cfd_targets.csv"):
            hints.append(
                {
                    "title": "CFD Target Priority",
                    "kind": "bar",
                    "table_key": "cfd/cfd_targets.csv",
                    "category_key": "target_name",
                    "value_key": "priority_rank",
                    "x_label": "Target",
                    "y_label": "Priority Rank",
                }
            )
        if has("cfd/cfd_operating_points.csv"):
            hints.extend(
                [
                    {
                        "title": "Mass Flow vs Chamber Pressure",
                        "kind": "scatter",
                        "table_key": "cfd/cfd_operating_points.csv",
                        "x_key": "chamber_pressure_pa",
                        "y_key": "mass_flow_kg_s",
                        "series_key": "target_name",
                        "x_label": "Chamber Pressure [Pa]",
                        "y_label": "Mass Flow [kg/s]",
                    },
                    {
                        "title": "Injector Inlet Pressure vs Chamber Pressure",
                        "kind": "scatter",
                        "table_key": "cfd/cfd_operating_points.csv",
                        "x_key": "chamber_pressure_pa",
                        "y_key": "injector_inlet_pressure_pa",
                        "series_key": "target_name",
                        "x_label": "Chamber Pressure [Pa]",
                        "y_label": "Injector Inlet Pressure [Pa]",
                    },
                ]
            )
    elif step in {"test_plan", "test_define_articles", "test_ingest_data", "test_compare_model", "test_calibrate_hotfire", "test_readiness"}:
        if has("testing/test_matrix.csv"):
            hints.extend(
                [
                    {
                        "title": "Planned Test Points by Stage",
                        "kind": "count_bar",
                        "table_key": "testing/test_matrix.csv",
                        "category_key": "intended_stage",
                        "x_label": "Stage",
                        "y_label": "Count",
                    },
                    {
                        "title": "Nominal Burn Time by Test Point",
                        "kind": "bar",
                        "table_key": "testing/test_matrix.csv",
                        "category_key": "point_id",
                        "value_key": "expected_burn_time_s",
                        "x_label": "Test Point",
                        "y_label": "Expected Burn Time [s]",
                    },
                ]
            )
        if has("testing/test_stages.csv"):
            hints.append(
                {
                    "title": "Stage Sequence",
                    "kind": "bar",
                    "table_key": "testing/test_stages.csv",
                    "category_key": "stage_name",
                    "value_key": "stage_order",
                    "x_label": "Stage",
                    "y_label": "Stage Order",
                }
            )
    return hints


def _config_snapshot(step: str) -> dict[str, Any] | None:
    config_key = CONFIG_STEP_KEYS.get(step)
    if not config_key:
        return None
    defaults = _default_payload()
    if config_key not in defaults:
        return None
    return {
        "title": _title_case_slug(config_key),
        "source": "Current default editor payload",
        "content": defaults[config_key],
    }


def _generic_step_metrics(
    node: Mapping[str, Any],
    *,
    downloads: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    svg_exports: list[dict[str, Any]],
    json_previews: list[dict[str, Any]],
    downstream: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        _metric_card("Step Kind", _title_case_slug(str(node.get("kind") or "workflow"))),
        _metric_card("Inputs", len(list(node.get("inputs") or []))),
        _metric_card("Outputs", len(list(node.get("outputs") or []))),
        _metric_card("Feeds Into", len(downstream)),
        _metric_card("Persisted Files", len(downloads)),
        _metric_card("CSV Sources", len(tables)),
        _metric_card("JSON Artifacts", len(json_previews)),
        _metric_card("SVG Exports", len(svg_exports)),
    ]


def _notes_from_json_previews(json_previews: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    for preview in json_previews:
        content = preview.get("content")
        if not isinstance(content, dict):
            continue
        for key in ("warnings", "notes", "outstanding_blockers"):
            values = content.get(key)
            if isinstance(values, list):
                notes.extend(str(value) for value in values if value not in {None, ""})
    return notes[:12]


def _step_metric_cards(
    step: str,
    root: Path | None,
    node: Mapping[str, Any],
    *,
    downloads: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    svg_exports: list[dict[str, Any]],
    json_previews: list[dict[str, Any]],
    downstream: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    section = STEP_SECTION_METRIC_SOURCE.get(step)
    if section and root is not None:
        metrics = _section_metric_cards(section, root)
        if metrics:
            return metrics
    return _generic_step_metrics(
        node,
        downloads=downloads,
        tables=tables,
        svg_exports=svg_exports,
        json_previews=json_previews,
        downstream=downstream,
    )


def _step_notes(
    step: str,
    root: Path | None,
    *,
    downloads: list[dict[str, Any]],
    json_previews: list[dict[str, Any]],
    config_snapshot: dict[str, Any] | None,
) -> list[str]:
    notes: list[str] = []
    section = STEP_SECTION_METRIC_SOURCE.get(step)
    if section and root is not None:
        notes.extend(_section_notes(section, root))
    notes.extend(_notes_from_json_previews(json_previews))
    if not downloads:
        if config_snapshot:
            notes.append("No persisted run artifacts are required for this node. The page shows the current default config payload.")
        else:
            notes.append("The latest run does not contain persisted artifacts for this step.")
    deduped: list[str] = []
    seen: set[str] = set()
    for note in notes:
        text = str(note).strip()
        if not text or text in seen:
            continue
        deduped.append(text)
        seen.add(text)
    return deduped[:12]


def _section_metric_cards(section: str, root: Path) -> list[dict[str, Any]]:
    if section == "thermal":
        sizing = _load_json_if_exists(root / section / "thermal_sizing.json") or {}
        return [
            _metric_card("Thermal Cases", len(sizing.get("case_summaries", []))),
            _metric_card("Thermal Valid", "Pass" if not sizing.get("warnings") else "Review"),
            _metric_card("Warnings", len(sizing.get("warnings", []))),
            _metric_card("Protection Mass", round(float(sizing.get("total_thermal_protection_mass_estimate_kg", 0.0)), 3), "kg"),
        ]
    if section == "nozzle_offdesign":
        results = _load_json_if_exists(root / section / "nozzle_offdesign_results.json") or {}
        return [
            _metric_card("Sea-Level Avg Thrust", round(float(results.get("sea_level_summary", {}).get("average_thrust_n", 0.0)), 1), "N"),
            _metric_card("Vacuum Avg Thrust", round(float(results.get("vacuum_summary", {}).get("average_thrust_n", 0.0)), 1), "N"),
            _metric_card("Warnings", len(results.get("warnings", []))),
            _metric_card("Recommendation Ready", "Yes" if results.get("validity_flags", {}).get("recommendation_identified") else "No"),
        ]
    if section == "cfd":
        plan = _load_json_if_exists(root / section / "cfd_campaign_plan.json") or {}
        return [
            _metric_card("CFD Targets", len(plan.get("targets", []))),
            _metric_card("Plan Valid", "Pass" if plan.get("cfd_plan_valid") else "Review"),
            _metric_card("Recommended Next Target", plan.get("recommended_next_target_name", "n/a")),
            _metric_card("Warnings", len(plan.get("warnings", []))),
        ]
    if section == "testing":
        readiness = _load_json_if_exists(root / section / "readiness_summary.json") or {}
        return [
            _metric_card("Overall Readiness", "Pass" if readiness.get("overall_readiness_flag") else "Hold"),
            _metric_card("Completed Stages", len(readiness.get("completed_stages", []))),
            _metric_card("Next Test", readiness.get("recommended_next_test", "n/a")),
            _metric_card("Blockers", len(readiness.get("outstanding_blockers", []))),
        ]
    return []


def _section_notes(section: str, root: Path) -> list[str]:
    if section == "thermal":
        sizing = _load_json_if_exists(root / section / "thermal_sizing.json") or {}
        return list(sizing.get("warnings", [])) + [
            f"{item['case_name']}: governing region {item['governing_region']}, minimum margin {item['minimum_margin_k']:.1f} K"
            for item in list(sizing.get("case_summaries", []))[:3]
            if isinstance(item, dict) and item.get("minimum_margin_k") is not None
        ]
    if section == "nozzle_offdesign":
        results = _load_json_if_exists(root / section / "nozzle_offdesign_results.json") or {}
        return list(results.get("warnings", []))
    if section == "cfd":
        plan = _load_json_if_exists(root / section / "cfd_campaign_plan.json") or {}
        return list(plan.get("notes", [])) + list(plan.get("warnings", []))
    if section == "testing":
        readiness = _load_json_if_exists(root / section / "readiness_summary.json") or {}
        return list(readiness.get("notes", [])) + list(readiness.get("outstanding_blockers", []))
    return []


def _section_interactive_charts(section: str, root: Path) -> list[dict[str, Any]]:
    charts: list[dict[str, Any]] = []
    if section == "thermal":
        rows = _read_csv_rows(root / section / "thermal_region_histories.csv")
        for title, y_key, y_label in [
            ("Heat Flux by Region", "heat_flux_w_m2", "Heat Flux [W/m^2]"),
            ("Inner Wall Temperature by Region", "inner_wall_temp_k", "Inner Wall Temperature [K]"),
            ("Outer Wall Temperature by Region", "outer_wall_temp_k", "Outer Wall Temperature [K]"),
        ]:
            chart = _numeric_series_chart(title, rows, x_key="time_s", y_key=y_key, series_key="region", x_label="Time [s]", y_label=y_label)
            if chart:
                charts.append(chart)
    elif section == "nozzle_offdesign":
        summary_rows = _read_csv_rows(root / section / "nozzle_operating_points.csv")
        transient_rows = _read_csv_rows(root / section / "nozzle_transient_offdesign.csv")
        for chart in [
            _category_bar_chart("Average Thrust by Environment", summary_rows, category_key="case_name", value_key="average_thrust_n", y_label="Average Thrust [N]"),
            _category_bar_chart("Average Isp by Environment", summary_rows, category_key="case_name", value_key="average_isp_s", y_label="Average Isp [s]"),
            _numeric_series_chart("Transient Thrust by Environment", transient_rows, x_key="time_s", y_key="thrust_n", series_key="case_name", x_label="Time [s]", y_label="Thrust [N]"),
        ]:
            if chart:
                charts.append(chart)
    elif section == "cfd":
        target_rows = _read_csv_rows(root / section / "cfd_targets.csv")
        operating_rows = _read_csv_rows(root / section / "cfd_operating_points.csv")
        for chart in [
            _category_bar_chart("CFD Target Priority", target_rows, category_key="target_name", value_key="priority_rank", y_label="Priority Rank"),
            _numeric_series_chart("Mass Flow vs Chamber Pressure", operating_rows, x_key="chamber_pressure_pa", y_key="mass_flow_kg_s", series_key="target_name", kind="scatter", x_label="Chamber Pressure [Pa]", y_label="Mass Flow [kg/s]"),
            _numeric_series_chart("Injector Inlet Pressure vs Chamber Pressure", operating_rows, x_key="chamber_pressure_pa", y_key="injector_inlet_pressure_pa", series_key="target_name", kind="scatter", x_label="Chamber Pressure [Pa]", y_label="Injector Inlet Pressure [Pa]"),
        ]:
            if chart:
                charts.append(chart)
    elif section == "testing":
        matrix_rows = _read_csv_rows(root / section / "test_matrix.csv")
        stage_rows = _read_csv_rows(root / section / "test_stages.csv")
        for chart in [
            _count_bar_chart("Planned Test Points by Stage", matrix_rows, category_key="intended_stage"),
            _category_bar_chart("Nominal Burn Time by Test Point", matrix_rows, category_key="point_id", value_key="expected_burn_time_s", y_label="Expected Burn Time [s]"),
            _category_bar_chart("Stage Sequence", stage_rows, category_key="stage_name", value_key="stage_order", y_label="Stage Order"),
        ]:
            if chart:
                charts.append(chart)
    return charts


def _latest_run_section_payload(section: str) -> dict[str, Any] | None:
    latest = _latest_run_payload()
    if not latest:
        return None
    root = Path(latest["root"])
    manifest = latest.get("manifest") or {}
    sections = dict(manifest.get("sections") or {})
    if section not in sections and not (root / section).exists():
        return None
    section_path = root / section
    svg_charts = []
    if section_path.exists():
        for path in sorted(section_path.glob("*.svg")):
            svg_charts.append(
                {
                    "title": _title_case_slug(path.stem),
                    "relative_path": path.relative_to(root).as_posix(),
                }
            )
    return {
        "run_id": latest.get("run_id"),
        "requested_mode": latest.get("requested_mode"),
        "root": latest.get("root"),
        "section": section,
        "title": _title_case_slug(section),
        "metrics": _section_metric_cards(section, root),
        "notes": _section_notes(section, root),
        "charts": _section_interactive_charts(section, root),
        "svg_charts": svg_charts,
        "downloads": _section_downloads(root, section),
    }


def _workflow_step_payload(step: str) -> dict[str, Any] | None:
    nodes = _workflow_nodes_by_id()
    node = nodes.get(step)
    if node is None:
        return None

    downstream = _workflow_downstream().get(step, [])
    config_snapshot = _config_snapshot(step)
    defaults = _default_payload()
    latest = _latest_step_run_payload(step) or _latest_run_payload()
    root: Path | None = None
    downloads: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    json_previews: list[dict[str, Any]] = []
    svg_exports: list[dict[str, Any]] = []
    chart_hints: list[dict[str, Any]] = []
    json_docs: list[tuple[str, Any]] = []
    csv_tables: list[dict[str, Any]] = []

    if latest:
        root = Path(latest["root"])
        artifacts = _step_artifacts(root, step)
        downloads = [
            {
                "label": str(artifact.get("filename") or Path(str(artifact.get("relative_path") or "")).name),
                "relative_path": str(artifact.get("relative_path") or ""),
                "extension": str(artifact.get("extension") or ""),
            }
            for artifact in artifacts
            if artifact.get("relative_path")
        ]
        tables = _step_tables(root, artifacts)
        json_previews = _json_artifact_previews(root, artifacts)
        svg_exports = _svg_exports(artifacts)
        chart_hints = _step_chart_hints(step, tables)
        json_docs = [(str(item.get("relative_path") or ""), item.get("content")) for item in json_previews if item.get("relative_path")]
        root_json_docs = _json_artifacts_for_root(root)
        json_docs.extend(item for item in root_json_docs if item[0] not in {doc[0] for doc in json_docs})
        csv_tables = [
            {
                "relative_path": table["relative_path"],
                "columns": table["columns"],
                "rows": table["rows"],
            }
            for table in tables
        ]
        seen_csv_paths = {table["relative_path"] for table in csv_tables}
        for table in _csv_tables_for_root(root):
            if table["relative_path"] not in seen_csv_paths:
                csv_tables.append(table)

    inputs = _resolved_io_items(
        list(node.get("inputs") or []),
        defaults=defaults,
        root=root,
        json_docs=json_docs,
        csv_tables=csv_tables,
    )
    outputs = _resolved_io_items(
        list(node.get("outputs") or []),
        defaults=defaults,
        root=root,
        json_docs=json_docs,
        csv_tables=csv_tables,
    )

    return {
        "run_id": None if latest is None else latest.get("run_id"),
        "requested_mode": None if latest is None else latest.get("requested_mode"),
        "root": None if latest is None else latest.get("root"),
        "step": step,
        "title": node["title"],
        "description": node.get("description"),
        "kind": node.get("kind"),
        "phase": node.get("phase"),
        "inputs": inputs,
        "outputs": outputs,
        "downstream": downstream,
        "detail_href": node.get("detail_href") or f"/simulation.html?step={step}",
        "metrics": _step_metric_cards(
            step,
            root,
            node,
            downloads=downloads,
            tables=tables,
            svg_exports=svg_exports,
            json_previews=json_previews,
            downstream=downstream,
        ),
        "notes": _step_notes(
            step,
            root,
            downloads=downloads,
            json_previews=json_previews,
            config_snapshot=config_snapshot,
        ),
        "config_snapshot": config_snapshot,
        "tables": tables,
        "chart_hints": chart_hints,
        "json_artifacts": json_previews,
        "svg_exports": svg_exports,
        "downloads": downloads,
    }


def _latest_run_dashboard(root: Path, manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    summary = dict((manifest or {}).get("summary") or {})
    geometry = _latest_geometry_payload(root)
    structural = _load_json_if_exists(root / "structural" / "structural_sizing.json")
    thermal = _load_json_if_exists(root / "thermal" / "thermal_sizing.json")
    nozzle = _load_json_if_exists(root / "nozzle_offdesign" / "nozzle_offdesign_results.json")
    nominal = _load_json_if_exists(root / "performance" / "nominal_metrics.json")

    metrics: list[dict[str, Any]] = []
    if geometry:
        if geometry.get("chamber_inner_diameter_excluding_liner_m") is not None:
            metrics.append(
                _metric_card(
                    "Chamber ID Excl. Liner",
                    round(float(geometry["chamber_inner_diameter_excluding_liner_m"]) * 1000.0, 1),
                    "mm",
                )
            )
        if geometry.get("chamber_outer_diameter_excluding_liner_m") is not None:
            metrics.append(
                _metric_card(
                    "Chamber OD Excl. Liner",
                    round(float(geometry["chamber_outer_diameter_excluding_liner_m"]) * 1000.0, 1),
                    "mm",
                )
            )
        if geometry.get("chamber_inner_diameter_including_liner_m") is not None:
            metrics.append(
                _metric_card(
                    "Chamber ID Incl. Liner",
                    round(float(geometry["chamber_inner_diameter_including_liner_m"]) * 1000.0, 1),
                    "mm",
                )
            )
        if geometry.get("chamber_outer_diameter_including_liner_m") is not None:
            metrics.append(
                _metric_card(
                    "Chamber OD Incl. Liner",
                    round(float(geometry["chamber_outer_diameter_including_liner_m"]) * 1000.0, 1),
                    "mm",
                )
            )
        if geometry.get("fuel_inner_diameter_m") is not None:
            metrics.append(_metric_card("Fuel ID", round(float(geometry["fuel_inner_diameter_m"]) * 1000.0, 1), "mm"))
        if geometry.get("fuel_outer_diameter_m") is not None:
            metrics.append(_metric_card("Fuel OD", round(float(geometry["fuel_outer_diameter_m"]) * 1000.0, 1), "mm"))
        if geometry.get("throat_diameter_m") is not None:
            metrics.append(_metric_card("Throat Diameter", round(float(geometry["throat_diameter_m"]) * 1000.0, 1), "mm"))
        if geometry.get("nozzle_exit_diameter_m") is not None:
            metrics.append(_metric_card("Exit Diameter", round(float(geometry["nozzle_exit_diameter_m"]) * 1000.0, 1), "mm"))
        if geometry.get("nozzle_length_m") is not None:
            metrics.append(_metric_card("Nozzle Length", round(float(geometry["nozzle_length_m"]) * 1000.0, 1), "mm"))
        if geometry.get("inner_liner_thickness_m") is not None:
            metrics.append(_metric_card("Liner Thickness", round(float(geometry["inner_liner_thickness_m"]) * 1000.0, 2), "mm"))
        if geometry.get("postchamber_length_m") is not None:
            metrics.append(_metric_card("Post Combustion Length", round(float(geometry["postchamber_length_m"]) * 1000.0, 1), "mm"))
        if geometry.get("prechamber_length_m") is not None:
            metrics.append(_metric_card("Pre Combustion Length", round(float(geometry["prechamber_length_m"]) * 1000.0, 1), "mm"))
        if geometry.get("converging_throat_half_angle_deg") is not None:
            metrics.append(_metric_card("Converging Half-Angle", round(float(geometry["converging_throat_half_angle_deg"]), 2), "deg"))
        if geometry.get("injector_hole_count") is not None:
            metrics.append(_metric_card("Injector Hole Count", int(geometry["injector_hole_count"])))
        if geometry.get("injector_total_hole_area_m2") is not None:
            metrics.append(
                _metric_card(
                    "Injector Total Hole Area",
                    round(float(geometry["injector_total_hole_area_m2"]) * 1.0e6, 3),
                    "mm^2",
                )
            )
    if nominal:
        if nominal.get("thrust_avg_n") is not None:
            metrics.append(_metric_card("Average Thrust", round(float(nominal["thrust_avg_n"]), 1), "N", emphasis="accent"))
        if nominal.get("pc_avg_bar") is not None:
            metrics.append(_metric_card("Average Chamber Pressure", round(float(nominal["pc_avg_bar"]), 2), "bar"))
    if structural and structural.get("total_structural_mass_estimate_kg") is not None:
        metrics.append(
            _metric_card(
                "Structural Mass",
                round(float(structural["total_structural_mass_estimate_kg"]), 3),
                "kg",
            )
        )
    if thermal and thermal.get("throat_region_result", {}).get("peak_inner_wall_temp_k") is not None:
        metrics.append(
            _metric_card(
                "Peak Throat Wall Temp",
                round(float(thermal["throat_region_result"]["peak_inner_wall_temp_k"]), 1),
                "K",
                emphasis="warning",
            )
        )
    if nozzle and nozzle.get("sea_level_summary", {}).get("average_thrust_n") is not None:
        metrics.append(
            _metric_card(
                "Sea-Level Avg Thrust",
                round(float(nozzle["sea_level_summary"]["average_thrust_n"]), 1),
                "N",
            )
        )
    if summary.get("recommended_next_stage") is not None:
        metrics.append(_metric_card("Recommended Next Stage", summary["recommended_next_stage"]))
    if summary.get("overall_readiness_flag") is not None:
        metrics.append(_metric_card("Overall Readiness", "Pass" if summary["overall_readiness_flag"] else "Hold"))

    return {
        "metrics": metrics,
        "summary_items": _summary_items(summary),
        "chart_groups": _chart_groups(root, manifest),
    }


def _default_payload() -> dict[str, Any]:
    design_override = _load_optional_json(INPUT_DIR / "design_config.json")
    design_config = deep_merge(load_project_defaults()["design_workflow"], design_override)
    study_config = build_design_config(design_config)
    hydraulic_override = _load_optional_json(INPUT_DIR / "hydraulic_validation_config.json")
    structural_override = _load_optional_json(INPUT_DIR / "structural_config.json")
    thermal_override = _load_optional_json(INPUT_DIR / "thermal_config.json")
    nozzle_offdesign_override = _load_optional_json(INPUT_DIR / "nozzle_offdesign_config.json")
    cfd_override = _load_optional_json(INPUT_DIR / "cfd_config.json")
    testing_override = _load_optional_json(INPUT_DIR / "test_campaign_config.json")
    cea_config = deep_merge(load_project_defaults()["cea"], _load_optional_json(INPUT_DIR / "cea_config.json"))
    return {
        "design_config": design_config,
        "cea_config": cea_config,
        "hydraulic_validation_config": normalize_hydraulic_validation_config(
            merge_hydraulic_validation_config(study_config, hydraulic_override),
            study_config,
        ),
        "structural_config": normalize_structural_config(
            merge_structural_config(study_config, structural_override),
            study_config,
        ),
        "thermal_config": normalize_thermal_config(
            merge_thermal_config(study_config, thermal_override),
            study_config,
        ),
        "nozzle_offdesign_config": normalize_nozzle_offdesign_config(
            merge_nozzle_offdesign_config(study_config, nozzle_offdesign_override),
            study_config,
        ),
        "cfd_config": normalize_cfd_config(
            merge_cfd_config(study_config, cfd_override),
            study_config,
        ),
        "testing_config": normalize_testing_config(
            merge_testing_config(study_config, testing_override),
            study_config,
        ),
        "output_dir": str(OUTPUT_DIR),
    }


def _latest_run_payload() -> dict[str, Any] | None:
    latest_path = OUTPUT_DIR / "latest_run.json"
    if not latest_path.exists():
        return None
    latest = load_json(latest_path)
    manifest_path = Path(latest["manifest_path"])
    latest["manifest"] = load_json(manifest_path) if manifest_path.exists() else None
    root = Path(latest["root"])
    latest["artifacts_by_section"] = group_artifacts_by_section(root)
    latest["dashboard"] = _latest_run_dashboard(root, latest["manifest"])
    return latest


def _latest_step_run_payload(step: str) -> dict[str, Any] | None:
    if step not in STEP_ARTIFACT_PREFIXES:
        return None
    runs_dir = OUTPUT_DIR / "runs"
    if not runs_dir.exists():
        return None
    best: dict[str, Any] | None = None
    best_key = ""
    for manifest_path in runs_dir.glob("*/manifest.json"):
        try:
            manifest = load_json(manifest_path)
        except Exception:
            continue
        if str(manifest.get("requested_mode") or "") != step:
            continue
        run_id = str(manifest.get("run_id") or manifest_path.parent.name)
        if run_id <= best_key:
            continue
        best_key = run_id
        best = {
            "run_id": run_id,
            "requested_mode": manifest.get("requested_mode"),
            "root": str(manifest_path.parent.resolve()),
            "manifest_path": str(manifest_path.resolve()),
            "manifest": manifest,
            "artifacts_by_section": group_artifacts_by_section(manifest_path.parent),
        }
    return best


def _latest_run_download_path(kind: str, relative_path: str | None = None) -> Path | None:
    latest = _latest_run_payload()
    if not latest:
        return None
    root = Path(latest["root"])
    if relative_path:
        candidate = (root / relative_path).resolve()
        if not str(candidate).startswith(str(root.resolve())) or not candidate.exists() or not candidate.is_file():
            return None
        return candidate
    mapping = {
        "combined_csv": root / "all_outputs.csv",
        "artifact_index_csv": root / "artifact_index.csv",
        "manifest_json": root / "manifest.json",
    }
    candidate = mapping.get(kind)
    if candidate is None or not candidate.exists():
        return None
    return candidate


def _job_snapshot() -> dict[str, Any]:
    with JOB_LOCK:
        return {
            "job_id": JOB_STATE["job_id"],
            "status": JOB_STATE["status"],
            "mode": JOB_STATE["mode"],
            "message": JOB_STATE["message"],
            "started_at": JOB_STATE["started_at"],
            "finished_at": JOB_STATE["finished_at"],
            "result": JOB_STATE["result"],
            "error": JOB_STATE["error"],
            "logs": list(JOB_STATE.get("logs", [])),
        }


def _set_job_state(**updates: Any) -> None:
    with JOB_LOCK:
        JOB_STATE.update(updates)


def _append_job_log(message: str, *, level: str = "info", job_id: int | None = None) -> None:
    text = str(message).strip()
    if not text:
        return
    with JOB_LOCK:
        if job_id is not None and JOB_STATE["job_id"] != job_id:
            return
        logs = list(JOB_STATE.get("logs", []))
        logs.append(
            {
                "timestamp": time.time(),
                "level": level,
                "message": text,
            }
        )
        JOB_STATE["logs"] = logs[-MAX_LOG_ENTRIES:]


class _JobLogStream(io.TextIOBase):
    def __init__(self, job_id: int, level: str) -> None:
        self._job_id = job_id
        self._level = level
        self._buffer = ""

    def write(self, text: str) -> int:
        if not text:
            return 0
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            _append_job_log(line, level=self._level, job_id=self._job_id)
        return len(text)

    def flush(self) -> None:
        if self._buffer:
            _append_job_log(self._buffer, level=self._level, job_id=self._job_id)
            self._buffer = ""


class _JobLogHandler(logging.Handler):
    def __init__(self, job_id: int) -> None:
        super().__init__(level=logging.INFO)
        self._job_id = job_id
        self.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:  # pragma: no cover - logging formatting failure
            self.handleError(record)
            return
        _append_job_log(message, level=record.levelname.lower(), job_id=self._job_id)


def _workflow_kwargs(payload: Mapping[str, Any], mode: str, output_dir: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "output_root": output_dir,
        "design_override": deepcopy(dict(payload.get("design_config") or {})) or None,
        "cea_override": deepcopy(dict(payload.get("cea_config") or {})) or None,
        "hydraulic_override": deepcopy(dict(payload.get("hydraulic_validation_config") or {})) or None,
        "structural_override": deepcopy(dict(payload.get("structural_config") or {})) or None,
        "thermal_override": deepcopy(dict(payload.get("thermal_config") or {})) or None,
        "nozzle_offdesign_override": deepcopy(dict(payload.get("nozzle_offdesign_config") or {})) or None,
        "cfd_override": deepcopy(dict(payload.get("cfd_config") or {})) or None,
        "testing_override": deepcopy(dict(payload.get("testing_config") or {})) or None,
    }


def _run_job(job_id: int, payload: Mapping[str, Any]) -> None:
    partial_result: dict[str, Any] | None = None
    configure_logging()
    root_logger = logging.getLogger()
    job_handler = _JobLogHandler(job_id)
    root_logger.addHandler(job_handler)
    try:
        mode = str(payload.get("mode", "")).strip()
        output_dir = str(payload.get("output_dir") or OUTPUT_DIR)
        run_all = bool(payload.get("run_all", False))

        if run_all:
            mode = "run_all"
            _append_job_log("Starting full workflow sequence.", job_id=job_id)
            _append_job_log(f"Sequence: {' -> '.join(RUN_ALL_SEQUENCE)}", job_id=job_id)
        else:
            _append_job_log(f"Starting selected workflow '{mode}'.", job_id=job_id)
        _append_job_log(f"Writing artifacts under {output_dir}.", job_id=job_id)
        if run_all:
            _append_job_log(
                "Run Full Sequence executes the default-safe workflow chain and skips modes that need external ingest files.",
                job_id=job_id,
            )
        else:
            _append_job_log(
                "The run button executes the selected mode only; later-stage modes may build prerequisites inside the same run.",
                job_id=job_id,
            )

        stdout_stream = _JobLogStream(job_id, "info")
        stderr_stream = _JobLogStream(job_id, "error")
        with contextlib.redirect_stdout(stdout_stream), contextlib.redirect_stderr(stderr_stream):
            if run_all:
                runs: list[dict[str, Any]] = []
                total = len(RUN_ALL_SEQUENCE)
                for index, sequence_mode in enumerate(RUN_ALL_SEQUENCE, start=1):
                    _append_job_log(f"[{index}/{total}] Starting '{sequence_mode}'.", job_id=job_id)
                    result = run_workflow(**_workflow_kwargs(payload, sequence_mode, output_dir))
                    manifest = load_json(result["run"].root / "manifest.json")
                    lines = summary_lines(result)
                    runs.append(
                        {
                            "mode": result["mode"],
                            "run_id": result["run"].run_id,
                            "run_root": str(result["run"].root),
                            "summary_lines": lines,
                            "manifest": manifest,
                        }
                    )
                    _append_job_log(f"[{index}/{total}] Completed '{sequence_mode}'.", job_id=job_id)
                    for line in lines:
                        _append_job_log(line, job_id=job_id)
                partial_result = {
                    "mode": "run_all",
                    "run_id": f"batch-{job_id}",
                    "run_root": str(Path(output_dir).resolve()),
                    "summary_lines": [
                        f"Completed {len(runs)} workflow modes in sequence.",
                        *[
                            f"{item['mode']}: {item['summary_lines'][0]}"
                            for item in runs
                            if item.get("summary_lines")
                        ],
                    ],
                    "runs": runs,
                    "manifest": runs[-1]["manifest"] if runs else None,
                }
            else:
                result = run_workflow(**_workflow_kwargs(payload, mode, output_dir))
                manifest = load_json(result["run"].root / "manifest.json")
                partial_result = {
                    "mode": result["mode"],
                    "run_id": result["run"].run_id,
                    "run_root": str(result["run"].root),
                    "summary_lines": summary_lines(result),
                    "manifest": manifest,
                }
        stdout_stream.flush()
        stderr_stream.flush()
        if run_all:
            _append_job_log("Full workflow sequence completed successfully.", job_id=job_id)
        else:
            _append_job_log(f"Workflow '{partial_result['mode']}' completed successfully.", job_id=job_id)
            _append_job_log(f"Run root: {partial_result['run_root']}", job_id=job_id)
        _set_job_state(
            status="completed",
            message="Full workflow sequence completed." if run_all else f"{partial_result['mode']} completed.",
            finished_at=time.time(),
            result=partial_result,
            error=None,
            traceback=None,
            thread=None,
        )
    except Exception as exc:  # pragma: no cover - exercised via manual UI use
        _append_job_log(f"Run failed: {exc}", level="error", job_id=job_id)
        _set_job_state(
            status="error",
            message=f"Run failed: {exc}",
            finished_at=time.time(),
            result=partial_result,
            error=str(exc),
            traceback=traceback.format_exc(),
            thread=None,
        )
        LOGGER.exception("Workflow UI job %s failed.", job_id)
    finally:
        root_logger.removeHandler(job_handler)
        job_handler.close()


def _start_job(payload: Mapping[str, Any], *, run_all: bool = False) -> dict[str, Any]:
    with JOB_LOCK:
        if JOB_STATE["status"] == "running":
            raise RuntimeError("Another workflow is already running.")
        job_id = int(JOB_STATE["job_id"]) + 1
        mode = "run_all" if run_all else str(payload.get("mode", "")).strip()
        worker_payload = dict(payload)
        if run_all:
            worker_payload["run_all"] = True
            worker_payload["mode"] = "run_all"
        worker = threading.Thread(target=_run_job, args=(job_id, worker_payload), name=f"workflow-{job_id}", daemon=True)
        JOB_STATE.update(
            {
                "job_id": job_id,
                "status": "running",
                "mode": mode,
                "message": "Running full workflow sequence..." if run_all else f"Running {mode}...",
                "started_at": time.time(),
                "finished_at": None,
                "result": None,
                "error": None,
                "traceback": None,
                "thread": worker,
                "logs": [],
            }
        )
    _append_job_log(
        "Queued full workflow sequence." if run_all else f"Queued workflow '{mode}'.",
        job_id=job_id,
    )
    worker.start()
    return _job_snapshot()


class WorkflowRequestHandler(BaseHTTPRequestHandler):
    server_version = "HybridWorkflowUI/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _write_json(self, payload: Mapping[str, Any] | list[Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, relative_path: str) -> None:
        target = (UI_DIR / relative_path.lstrip("/")).resolve()
        if not str(target).startswith(str(UI_DIR.resolve())) or not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = "text/plain; charset=utf-8"
        if target.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif target.suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif target.suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        elif target.suffix == ".png":
            content_type = "image/png"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_download(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        disposition = "inline" if path.suffix == ".svg" else "attachment"
        self.send_header("Content-Disposition", f'{disposition}; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        if route == "/":
            self._serve_file("index.html")
            return
        if route == "/api/default-config":
            self._write_json(_default_payload())
            return
        if route == "/api/workflow-modes":
            self._write_json({"modes": mode_definitions_payload()})
            return
        if route == "/api/workflow-map":
            self._write_json(workflow_map_payload())
            return
        if route == "/api/job-status":
            self._write_json(_job_snapshot())
            return
        if route == "/api/latest-run":
            self._write_json({"latest_run": _latest_run_payload()})
            return
        if route == "/api/latest-run-section":
            query = parse_qs(parsed.query)
            section = query.get("section", [""])[0]
            payload = _latest_run_section_payload(section)
            if payload is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._write_json(payload)
            return
        if route == "/api/workflow-step":
            query = parse_qs(parsed.query)
            step = query.get("step", [""])[0]
            payload = _workflow_step_payload(step)
            if payload is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._write_json(payload)
            return
        if route == "/api/latest-run-download":
            query = parse_qs(parsed.query)
            kind = query.get("kind", ["combined_csv"])[0]
            relative_path = query.get("relative_path", [None])[0]
            download_path = _latest_run_download_path(kind, relative_path)
            if download_path is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            if download_path.suffix == ".json":
                content_type = "application/json; charset=utf-8"
            elif download_path.suffix == ".svg":
                content_type = "image/svg+xml; charset=utf-8"
            elif download_path.suffix == ".txt":
                content_type = "text/plain; charset=utf-8"
            else:
                content_type = "text/csv; charset=utf-8"
            self._serve_download(download_path, content_type)
            return
        self._serve_file(route.lstrip("/"))

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        try:
            if route == "/api/run-workflow":
                self._write_json(_start_job(payload), status=HTTPStatus.ACCEPTED)
                return
            if route == "/api/run-all":
                self._write_json(_start_job(payload, run_all=True), status=HTTPStatus.ACCEPTED)
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._write_json(
                {"error": str(exc), "traceback": traceback.format_exc()},
                status=HTTPStatus.BAD_REQUEST,
            )


def main() -> None:
    configure_logging()
    server = ThreadingHTTPServer((HOST, PORT), WorkflowRequestHandler)
    LOGGER.info("Workflow UI available at http://%s:%s", HOST, PORT)
    server.serve_forever()
