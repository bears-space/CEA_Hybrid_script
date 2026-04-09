"""Top-level case runner utilities for nominal Step 1 studies."""

from __future__ import annotations

from typing import Any, Mapping

from src.analysis.constraints import evaluate_constraints
from src.analysis.metrics import extract_case_metrics
from src.simulation.solver_0d import run_0d_case


def run_nominal_case(config: Mapping[str, Any]) -> dict[str, Any]:
    result = run_0d_case(config)
    metrics = extract_case_metrics(result, config)
    constraints = evaluate_constraints(metrics, config.get("constraints", {}))
    return {
        "result": result,
        "metrics": metrics,
        "constraints": constraints,
    }
