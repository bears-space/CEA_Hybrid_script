"""Top-level case runner utilities for nominal Step 1 studies."""

from __future__ import annotations

from typing import Any, Mapping

from src.analysis.ballistics_comparison import comparison_summary
from src.analysis.constraints import evaluate_constraints
from src.analysis.metrics import extract_case_metrics
from src.simulation.solver_0d import run_0d_case
from src.simulation.solver_1d import run_1d_ballistics_case
from src.sizing.geometry_types import GeometryDefinition


def run_nominal_case(config: Mapping[str, Any]) -> dict[str, Any]:
    result = run_0d_case(config)
    metrics = extract_case_metrics(result, config)
    constraints = evaluate_constraints(metrics, config.get("constraints", {}))
    return {
        "result": result,
        "metrics": metrics,
        "constraints": constraints,
    }


def run_ballistics_case(
    config: Mapping[str, Any],
    geometry: GeometryDefinition,
    *,
    cea_data: Mapping[str, Any] | None = None,
    compare_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result = run_1d_ballistics_case(config, geometry, cea_data=cea_data)
    metrics = extract_case_metrics(result, config)
    constraints = evaluate_constraints(metrics, config.get("constraints", {}))
    comparison = None
    if compare_payload is not None:
        comparison = comparison_summary(compare_payload["metrics"], metrics)
        result["comparison"] = comparison
    return {
        "result": result,
        "metrics": metrics,
        "constraints": constraints,
        "comparison": comparison,
    }
