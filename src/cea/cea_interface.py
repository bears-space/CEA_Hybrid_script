"""High-level CEA module interface for both standalone and imported workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.cea_hybrid.defaults import get_default_raw_config

from src.io_utils import deep_merge
from src.cea.cea_runner import run_cea_case, run_cea_sweep, write_cea_outputs
from src.cea.cea_types import CEAPerformancePoint, CEASweepResult
from src.io_utils import load_json


def load_cea_config(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        return get_default_raw_config()
    return deep_merge(get_default_raw_config(), load_json(path))


def run_cea_study(raw_config: Mapping[str, Any] | None = None) -> CEASweepResult:
    return run_cea_sweep(raw_config or get_default_raw_config())


def get_cea_performance_point(result: CEASweepResult | list[CEAPerformancePoint], selector: str = "highest_isp") -> CEAPerformancePoint:
    cases = result.cases if isinstance(result, CEASweepResult) else list(result)
    if not cases:
        raise ValueError("No CEA cases are available.")
    if selector == "highest_isp":
        return max(cases, key=lambda case: case.isp_s)
    raise ValueError(f"Unsupported CEA selector: {selector}")


__all__ = [
    "CEAPerformancePoint",
    "CEASweepResult",
    "get_cea_performance_point",
    "load_cea_config",
    "run_cea_case",
    "run_cea_study",
    "write_cea_outputs",
]

