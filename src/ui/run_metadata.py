"""Helpers for browsing run-scoped artifact metadata."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def group_artifacts_by_section(root: Path) -> dict[str, list[dict[str, Any]]]:
    """Group artifact-index rows by section for UI browsing."""

    artifact_index_path = root / "artifact_index.csv"
    if not artifact_index_path.exists():
        return {}
    groups: dict[str, list[dict[str, Any]]] = {}
    with artifact_index_path.open("r", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            section = str(row.get("section") or "run_root")
            groups.setdefault(section, []).append(dict(row))
    return groups
