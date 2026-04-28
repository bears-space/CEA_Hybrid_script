"""Basic dataset cleaning, alignment, and trimming helpers."""

from __future__ import annotations

from typing import Mapping

import numpy as np

from src.testing.ignition_analysis import detect_burn_window, detect_ignition_time_s
from src.testing.test_types import TestDataset


def clean_test_dataset(dataset: TestDataset, testing_config: Mapping[str, object]) -> TestDataset:
    """Return a cleaned dataset with zeroed time and a trimmed burn window."""

    settings = dict(testing_config.get("data_cleaning", {}))
    padding_pre_s = float(settings.get("padding_pre_s", 0.05))
    padding_post_s = float(settings.get("padding_post_s", 0.05))

    channels = {key: list(values) for key, values in dataset.time_series_channels.items()}
    time_s = np.asarray(channels.get("time_s", []), dtype=float)
    notes = list(dataset.cleaning_notes)
    flags = dict(dataset.validity_flags)
    if time_s.size == 0:
        notes.append("Dataset has no time_s channel; skipping cleaning.")
        flags["cleaning_successful"] = False
        return TestDataset(
            run_id=dataset.run_id,
            article_id=dataset.article_id,
            stage_name=dataset.stage_name,
            data_source=dataset.data_source,
            file_references=list(dataset.file_references),
            time_series_channels=dict(dataset.time_series_channels),
            metadata=dict(dataset.metadata),
            cleaned_time_series_channels={},
            cleaning_notes=notes,
            validity_flags=flags,
        )

    order = np.argsort(time_s)
    zeroed_time_s = time_s[order] - float(time_s[order][0])
    sorted_channels: dict[str, list[float]] = {}
    for key, values in channels.items():
        array = np.asarray(values, dtype=float)
        if array.size == time_s.size:
            sorted_channels[key] = array[order].tolist()
    sorted_channels["time_s"] = zeroed_time_s.tolist()

    ignition_time_s = detect_ignition_time_s(sorted_channels)
    burn_start_s, burn_end_s = detect_burn_window(sorted_channels)
    if burn_start_s is None or burn_end_s is None:
        trimmed = dict(sorted_channels)
        notes.append("No active burn window detected; retained the full dataset.")
    else:
        start_time_s = max(burn_start_s - padding_pre_s, 0.0)
        end_time_s = burn_end_s + padding_post_s
        mask = (zeroed_time_s >= start_time_s) & (zeroed_time_s <= end_time_s)
        trimmed = {
            key: np.asarray(values, dtype=float)[mask].tolist()
            for key, values in sorted_channels.items()
            if len(values) == len(zeroed_time_s)
        }
        trimmed["time_s"] = (np.asarray(trimmed.get("time_s", []), dtype=float) - start_time_s).tolist()
        notes.append(f"Trimmed dataset to [{start_time_s:.4f}, {end_time_s:.4f}] s around the detected active window.")

    metadata = dict(dataset.metadata)
    metadata.setdefault("ignition_time_s", ignition_time_s)
    metadata.setdefault("burn_window_start_s", burn_start_s)
    metadata.setdefault("burn_window_end_s", burn_end_s)
    flags["cleaning_successful"] = True
    return TestDataset(
        run_id=dataset.run_id,
        article_id=dataset.article_id,
        stage_name=dataset.stage_name,
        data_source=dataset.data_source,
        file_references=list(dataset.file_references),
        time_series_channels=dict(dataset.time_series_channels),
        metadata=metadata,
        cleaned_time_series_channels=trimmed,
        cleaning_notes=notes,
        validity_flags=flags,
    )
