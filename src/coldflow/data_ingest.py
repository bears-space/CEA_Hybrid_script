"""Cold-flow dataset ingestion from CSV and JSON sources."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Mapping

from src.coldflow.coldflow_types import ColdFlowDataset, ColdFlowPoint, ColdFlowRigDefinition
from src.coldflow.data_schema import FIELD_ALIASES, OPTIONAL_POINT_FIELDS, apply_unit_scale, configured_aliases, normalize_column_name


def _raw_rows_from_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _raw_payload_from_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _unit_scale_for_field(field_name: str, ingest_config: Mapping[str, Any], default_scale: float | tuple[float, float]) -> float | tuple[float, float]:
    raw_override = dict(ingest_config.get("unit_overrides", {})).get(field_name)
    if raw_override is None:
        return default_scale
    if isinstance(raw_override, (int, float)):
        return float(raw_override)
    unit = normalize_column_name(str(raw_override))
    if unit == "pa":
        return 1.0
    if unit == "kpa":
        return 1.0e3
    if unit == "mpa":
        return 1.0e6
    if unit == "bar":
        return 1.0e5
    if unit == "kg_s":
        return 1.0
    if unit == "g_s":
        return 1.0e-3
    if unit == "kg_m3":
        return 1.0
    if unit == "g_cc":
        return 1.0e3
    if unit == "k":
        return 1.0
    if unit == "c":
        return (1.0, 273.15)
    raise ValueError(f"Unsupported unit override for cold-flow field '{field_name}': {raw_override}")


def _resolve_value(row: Mapping[str, Any], field_name: str, ingest_config: Mapping[str, Any]) -> Any:
    column_map = {key: str(value) for key, value in dict(ingest_config.get("column_map", {})).items()}
    if field_name in column_map:
        column_name = column_map[field_name]
        if column_name not in row:
            return None
        value = row[column_name]
        if value in ("", None):
            return None
        scale = _unit_scale_for_field(field_name, ingest_config, 1.0)
        if field_name in {"test_id", "timestamp", "fluid_name", "notes"}:
            return str(value)
        if field_name == "point_index":
            return int(value)
        return apply_unit_scale(value, scale)

    aliases = list(FIELD_ALIASES.get(field_name, ()))
    aliases.extend(
        configured_aliases(dict(ingest_config.get("field_aliases", {})).get(field_name, []))
    )
    normalized_row = {normalize_column_name(key): value for key, value in row.items()}
    for alias, default_scale in aliases:
        if alias not in normalized_row:
            continue
        value = normalized_row[alias]
        if value in ("", None):
            return None
        scale = _unit_scale_for_field(field_name, ingest_config, default_scale)
        if field_name in {"test_id", "timestamp", "fluid_name", "notes"}:
            return str(value)
        if field_name == "point_index":
            return int(value)
        return apply_unit_scale(value, scale)
    return None


def _extract_uncertainty(row: Mapping[str, Any]) -> dict[str, float]:
    uncertainty: dict[str, float] = {}
    for key, value in row.items():
        normalized = normalize_column_name(key)
        if not normalized.startswith("uncertainty_") or value in ("", None):
            continue
        uncertainty[normalized.removeprefix("uncertainty_")] = float(value)
    return uncertainty


def _point_from_row(
    row: Mapping[str, Any],
    *,
    row_index: int,
    coldflow_config: Mapping[str, Any],
    dataset_name: str,
) -> ColdFlowPoint:
    ingest_config = dict(coldflow_config.get("ingest", {}))
    values = {
        field_name: _resolve_value(row, field_name, ingest_config)
        for field_name in OPTIONAL_POINT_FIELDS
    }
    measurement_uncertainty = _extract_uncertainty(row)
    default_fluid = dict(coldflow_config.get("fluid", {}))
    test_id = str(values["test_id"] or f"{dataset_name}_{row_index:03d}")
    return ColdFlowPoint(
        test_id=test_id,
        point_index=int(values["point_index"]) if values["point_index"] is not None else row_index,
        timestamp=values["timestamp"],
        fluid_name=str(values["fluid_name"] or default_fluid.get("name") or "").strip() or None,
        fluid_temperature_k=(
            float(values["fluid_temperature_k"])
            if values["fluid_temperature_k"] is not None
            else (
                float(default_fluid["temperature_k"])
                if default_fluid.get("temperature_k") is not None
                else None
            )
        ),
        fluid_density_kg_m3=(
            float(values["fluid_density_kg_m3"])
            if values["fluid_density_kg_m3"] is not None
            else (
                float(default_fluid["density_kg_m3"])
                if default_fluid.get("density_kg_m3") is not None
                else None
            )
        ),
        upstream_pressure_pa=float(values["upstream_pressure_pa"]) if values["upstream_pressure_pa"] is not None else None,
        injector_inlet_pressure_pa=(
            float(values["injector_inlet_pressure_pa"])
            if values["injector_inlet_pressure_pa"] is not None
            else None
        ),
        downstream_pressure_pa=(
            float(values["downstream_pressure_pa"])
            if values["downstream_pressure_pa"] is not None
            else None
        ),
        measured_delta_p_feed_pa=(
            float(values["measured_delta_p_feed_pa"])
            if values["measured_delta_p_feed_pa"] is not None
            else None
        ),
        measured_delta_p_injector_pa=(
            float(values["measured_delta_p_injector_pa"])
            if values["measured_delta_p_injector_pa"] is not None
            else None
        ),
        measured_mdot_kg_s=float(values["measured_mdot_kg_s"]) if values["measured_mdot_kg_s"] is not None else None,
        measurement_uncertainty=measurement_uncertainty,
        notes=values["notes"],
    )


def _validate_points(points: list[ColdFlowPoint], dataset_name: str) -> list[str]:
    warnings: list[str] = []
    if not points:
        raise ValueError(f"Cold-flow dataset '{dataset_name}' did not contain any data points.")
    for point in points:
        if point.measured_mdot_kg_s is None:
            raise ValueError(f"Cold-flow point '{point.test_id}' is missing measured mass flow.")
        if point.downstream_pressure_pa is None:
            raise ValueError(f"Cold-flow point '{point.test_id}' is missing downstream pressure.")
        if point.upstream_pressure_pa is None and point.injector_inlet_pressure_pa is None:
            raise ValueError(
                f"Cold-flow point '{point.test_id}' must provide upstream pressure or injector inlet pressure."
            )
        if point.fluid_density_kg_m3 is None:
            warnings.append(
                f"Cold-flow point '{point.test_id}' does not define fluid density directly; predictor will require a configured default density."
            )
    return warnings


def _rig_definition_from_config(coldflow_config: Mapping[str, Any]) -> ColdFlowRigDefinition:
    rig_section = dict(coldflow_config.get("rig", {}))
    rig_section.setdefault("test_mode", str(coldflow_config.get("test_mode", "feed_plus_injector_rig")))
    rig_section.setdefault(
        "injector_geometry_reference",
        coldflow_config.get("injector_geometry_path"),
    )
    return ColdFlowRigDefinition.from_mapping(rig_section)


def load_coldflow_dataset(path: str | Path, coldflow_config: Mapping[str, Any]) -> ColdFlowDataset:
    """Load a cold-flow dataset from CSV or JSON into the typed internal representation."""

    source_path = Path(path)
    dataset_name = str(coldflow_config.get("dataset_name") or source_path.stem)
    dataset_format = str(coldflow_config.get("dataset_format", "auto")).lower()
    if dataset_format == "auto":
        dataset_format = source_path.suffix.lower().lstrip(".")
    if dataset_format not in {"csv", "json"}:
        raise ValueError(f"Unsupported cold-flow dataset format: {dataset_format}")

    warnings = list(coldflow_config.get("warnings", []))
    if dataset_format == "csv":
        raw_rows = _raw_rows_from_csv(source_path)
        points = [
            _point_from_row(row, row_index=index, coldflow_config=coldflow_config, dataset_name=dataset_name)
            for index, row in enumerate(raw_rows)
        ]
    else:
        payload = _raw_payload_from_json(source_path)
        if isinstance(payload, list):
            raw_rows = [dict(item) for item in payload]
            metadata = {}
            rig_definition = _rig_definition_from_config(coldflow_config)
        else:
            raw_rows = [dict(item) for item in payload.get("points", [])]
            metadata = dict(payload.get("metadata", {}))
            rig_definition = ColdFlowRigDefinition.from_mapping(
                dict(payload.get("rig_definition", _rig_definition_from_config(coldflow_config).to_dict()))
            )
        points = [
            _point_from_row(row, row_index=index, coldflow_config=coldflow_config, dataset_name=dataset_name)
            for index, row in enumerate(raw_rows)
        ]
        dataset = ColdFlowDataset(
            dataset_name=dataset_name,
            test_mode=str(coldflow_config.get("test_mode", rig_definition.test_mode)),
            points=points,
            rig_definition=rig_definition,
            metadata={
                **metadata,
                "source_path": str(source_path),
                "dataset_format": dataset_format,
            },
            warnings=[*warnings, *_validate_points(points, dataset_name)],
        )
        return dataset

    rig_definition = _rig_definition_from_config(coldflow_config)
    return ColdFlowDataset(
        dataset_name=dataset_name,
        test_mode=str(coldflow_config.get("test_mode", rig_definition.test_mode)),
        points=points,
        rig_definition=rig_definition,
        metadata={
            "source_path": str(source_path),
            "dataset_format": dataset_format,
        },
        warnings=[*warnings, *_validate_points(points, dataset_name)],
    )
