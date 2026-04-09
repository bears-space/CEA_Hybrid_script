"""Constraint evaluation helpers for nominal, sensitivity, and corner-case runs."""

from __future__ import annotations

from typing import Any, Mapping


def evaluate_constraints(metrics: Mapping[str, Any], constraints: Mapping[str, Any]) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    all_pass = True

    for key, rule in constraints.items():
        value = metrics.get(key)
        passed = True
        if "min" in rule:
            passed = passed and value is not None and value >= rule["min"]
        if "max" in rule:
            passed = passed and value is not None and value <= rule["max"]
        if "allowed" in rule:
            passed = passed and value in set(rule["allowed"])
        checks[key] = {
            "value": value,
            "passed": bool(passed),
            "rule": dict(rule),
        }
        all_pass = all_pass and bool(passed)

    return {
        "checks": checks,
        "all_pass": all_pass,
    }
