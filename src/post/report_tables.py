"""Report-table helpers for output export paths."""

from __future__ import annotations

from typing import Any, Mapping


def metrics_report_table(metrics: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"metric": key, "value": value} for key, value in metrics.items()]
