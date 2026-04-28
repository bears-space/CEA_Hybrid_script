"""Ingestion of summarized external CFD results from JSON or CSV."""

from __future__ import annotations

import csv
from pathlib import Path

from src.cfd.cfd_types import CfdResultSummary
from src.io_utils import load_json


def _json_entries(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if isinstance(payload.get("results"), list):
            return payload["results"]
        if "case_id" in payload:
            return [payload]
    return []


def _summary_from_csv_rows(rows: list[dict[str, str]], result_source: str) -> list[CfdResultSummary]:
    grouped: dict[str, dict] = {}
    for row in rows:
        case_id = str(row.get("case_id", "")).strip() or "unassigned_case"
        summary = grouped.setdefault(
            case_id,
            {
                "case_id": case_id,
                "solver_used": row.get("solver_used") or None,
                "completion_status": row.get("completion_status") or "completed",
                "result_source": result_source,
                "extracted_key_outputs": {},
                "comparison_to_reduced_order": {"corrections": []},
                "warnings": [],
                "notes": [],
            },
        )
        correction_type = str(row.get("correction_type", "")).strip()
        scalar_value = row.get("scalar_value")
        if correction_type and scalar_value not in {None, ""}:
            summary["extracted_key_outputs"][correction_type] = float(scalar_value)
            summary["comparison_to_reduced_order"]["corrections"].append(
                {
                    "correction_type": correction_type,
                    "downstream_target_module": row.get("downstream_target_module") or "",
                    "scalar_value": float(scalar_value),
                    "valid_operating_range": {
                        "minimum_chamber_pressure_pa": (
                            None if not row.get("minimum_chamber_pressure_pa") else float(row["minimum_chamber_pressure_pa"])
                        ),
                        "maximum_chamber_pressure_pa": (
                            None if not row.get("maximum_chamber_pressure_pa") else float(row["maximum_chamber_pressure_pa"])
                        ),
                        "minimum_mass_flow_kg_s": None if not row.get("minimum_mass_flow_kg_s") else float(row["minimum_mass_flow_kg_s"]),
                        "maximum_mass_flow_kg_s": None if not row.get("maximum_mass_flow_kg_s") else float(row["maximum_mass_flow_kg_s"]),
                    },
                }
            )
        if row.get("warning"):
            summary["warnings"].append(str(row["warning"]))
        if row.get("notes"):
            summary["notes"].append(str(row["notes"]))
    return [CfdResultSummary.from_mapping(item) for item in grouped.values()]


def load_cfd_result_summaries(path: str | Path) -> list[CfdResultSummary]:
    """Load summarized CFD result data from JSON or CSV."""

    result_path = Path(path)
    if not result_path.exists():
        raise FileNotFoundError(f"CFD result summary file not found: {result_path}")
    if result_path.suffix.lower() == ".json":
        payload = load_json(result_path)
        entries = _json_entries(payload)
        return [
            CfdResultSummary.from_mapping(
                {
                    **dict(entry),
                    "result_source": str(dict(entry).get("result_source", result_path.name)),
                }
            )
            for entry in entries
        ]
    if result_path.suffix.lower() == ".csv":
        with result_path.open("r", newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        return _summary_from_csv_rows(rows, result_path.name)
    raise ValueError("CFD result ingest currently supports only JSON and CSV summary files.")
