"""Summary row builders shared by CSV export paths."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def metrics_to_row(case_name: str, metrics: Mapping[str, Any], constraints: Mapping[str, Any] | None = None) -> dict[str, Any]:
    row = {"case_name": case_name, **metrics}
    if constraints is not None:
        row["constraints_all_pass"] = constraints.get("all_pass")
    return row


def constraint_rows(constraints: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, payload in constraints.get("checks", {}).items():
        rule = payload.get("rule", {})
        rows.append(
            {
                "constraint": key,
                "passed": payload.get("passed"),
                "value": payload.get("value"),
                "min": rule.get("min"),
                "max": rule.get("max"),
                "allowed": ", ".join(map(str, rule.get("allowed", []))) if "allowed" in rule else None,
            }
        )
    return rows


def oat_case_rows(entries: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(entry) for entry in entries]
