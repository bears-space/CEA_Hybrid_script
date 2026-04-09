"""Structured state objects for the modular 0D simulation layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ZeroDCaseArtifacts:
    seed_case: dict[str, Any]
    runtime_inputs: dict[str, Any] | None = None
    raw_history: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
