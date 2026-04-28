"""Measured test-data ingestion helpers for JSON and CSV sources."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.io_utils import load_json
from src.testing.test_types import InstrumentationPlan, TestDataset


def _as_float_list(values: Iterable[Any]) -> list[float]:
    materialized: list[float] = []
    for value in values:
        try:
            materialized.append(float(value))
        except (TypeError, ValueError):
            continue
    return materialized


def _mapped_channels(raw: Mapping[str, Any], channel_map: Mapping[str, str]) -> dict[str, list[float]]:
    mapped: dict[str, list[float]] = {}
    for raw_name, raw_values in raw.items():
        name = str(channel_map.get(raw_name, raw_name))
        if isinstance(raw_values, list):
            mapped[name] = _as_float_list(raw_values)
    return mapped


def _validate_dataset_channels(dataset: TestDataset, plan_map: Mapping[str, InstrumentationPlan]) -> TestDataset:
    flags = dict(dataset.validity_flags)
    flags.setdefault("has_time_channel", "time_s" in dataset.time_series_channels)
    plan = plan_map.get(dataset.article_id)
    if plan is None:
        flags.setdefault("article_plan_available", False)
        return TestDataset(
            run_id=dataset.run_id,
            article_id=dataset.article_id,
            stage_name=dataset.stage_name,
            data_source=dataset.data_source,
            file_references=list(dataset.file_references),
            time_series_channels=dict(dataset.time_series_channels),
            metadata=dict(dataset.metadata),
            cleaned_time_series_channels=dict(dataset.cleaned_time_series_channels),
            cleaning_notes=list(dataset.cleaning_notes),
            validity_flags=flags,
        )
    flags["article_plan_available"] = True
    for channel_name in plan.required_core_channels:
        flags[f"has_required_channel::{channel_name}"] = channel_name in dataset.time_series_channels
    return TestDataset(
        run_id=dataset.run_id,
        article_id=dataset.article_id,
        stage_name=dataset.stage_name,
        data_source=dataset.data_source,
        file_references=list(dataset.file_references),
        time_series_channels=dict(dataset.time_series_channels),
        metadata=dict(dataset.metadata),
        cleaned_time_series_channels=dict(dataset.cleaned_time_series_channels),
        cleaning_notes=list(dataset.cleaning_notes),
        validity_flags=flags,
    )


def _load_json_datasets(path: Path, channel_map: Mapping[str, str]) -> list[TestDataset]:
    payload = load_json(path)
    if isinstance(payload, dict) and "datasets" in payload:
        items = list(payload["datasets"])
    elif isinstance(payload, list):
        items = list(payload)
    else:
        items = [payload]
    datasets: list[TestDataset] = []
    for index, item in enumerate(items):
        channels = _mapped_channels(
            item.get("time_series_channels", item.get("channels", {})),
            channel_map,
        )
        datasets.append(
            TestDataset(
                run_id=str(item.get("run_id", f"{path.stem}_{index + 1}")),
                article_id=str(item.get("article_id", "")),
                stage_name=str(item.get("stage_name", "")),
                data_source="json",
                file_references=[str(path)],
                time_series_channels=channels,
                metadata=dict(item.get("metadata", {})),
            )
        )
    return datasets


def _load_csv_dataset(path: Path, testing_config: Mapping[str, Any]) -> TestDataset:
    ingest = dict(testing_config.get("ingest", {}))
    channel_map = {str(key): str(value) for key, value in dict(ingest.get("channel_map", {})).items()}
    metadata_defaults = dict(ingest.get("dataset_metadata_defaults", {}))
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    channels: dict[str, list[float]] = {}
    if rows:
        for raw_name in rows[0]:
            name = str(channel_map.get(raw_name, raw_name))
            channels[name] = _as_float_list(row.get(raw_name) for row in rows)
    return TestDataset(
        run_id=str(metadata_defaults.get("run_id", path.stem)),
        article_id=str(metadata_defaults.get("article_id", "")),
        stage_name=str(metadata_defaults.get("stage_name", "")),
        data_source="csv",
        file_references=[str(path)],
        time_series_channels=channels,
        metadata=metadata_defaults,
    )


def load_test_datasets(
    testing_config: Mapping[str, Any],
    instrumentation_plans: list[InstrumentationPlan],
) -> tuple[list[TestDataset], list[str]]:
    """Load configured measured datasets and validate them against the plan."""

    dataset_path = str(testing_config.get("dataset_path", "")).strip()
    if not dataset_path:
        return [], ["No testing dataset path configured; campaign planning will proceed without ingested test data."]
    path = Path(dataset_path)
    if not path.exists():
        return [], [f"Testing dataset path does not exist: {path}"]

    ingest = dict(testing_config.get("ingest", {}))
    channel_map = {str(key): str(value) for key, value in dict(ingest.get("channel_map", {})).items()}
    files = [path] if path.is_file() else sorted(candidate for candidate in path.iterdir() if candidate.suffix.lower() in {".json", ".csv"})
    datasets: list[TestDataset] = []
    warnings: list[str] = []
    for file_path in files:
        if file_path.suffix.lower() == ".json":
            datasets.extend(_load_json_datasets(file_path, channel_map))
        elif file_path.suffix.lower() == ".csv":
            datasets.append(_load_csv_dataset(file_path, testing_config))
        else:
            warnings.append(f"Unsupported testing dataset file skipped: {file_path}")

    plan_map = {plan.article_id: plan for plan in instrumentation_plans}
    validated = [_validate_dataset_channels(dataset, plan_map) for dataset in datasets]
    return validated, warnings
