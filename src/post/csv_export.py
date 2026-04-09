"""CSV export helpers for the modular workflow outputs."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, Mapping


def _fieldnames(rows: list[Mapping[str, Any]]) -> list[str]:
    seen: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.append(key)
    return seen


def write_rows_csv(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    materialized = [dict(row) for row in rows]
    fieldnames = _fieldnames(materialized)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(materialized)
    return destination


def write_mapping_csv(path: str | Path, payload: Mapping[str, Any], key_name: str = "key", value_name: str = "value") -> Path:
    rows = [{key_name: key, value_name: value} for key, value in payload.items()]
    return write_rows_csv(path, rows)
