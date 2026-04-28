"""Run-scoped output layout for workflow artifacts."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.constants import OUTPUT_ROOT, REPORTS_DIRNAME, RUNS_DIRNAME
from src.io_utils import ensure_directory, sanitize_filename, write_json

LOGGER = logging.getLogger(__name__)


def _section_name_for_path(root: Path, file_path: Path) -> str:
    relative = file_path.relative_to(root)
    return relative.parts[0] if len(relative.parts) > 1 else "run_root"


def _iter_run_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def write_artifact_index_csv(root: Path, run_files: Sequence[Path] | None = None) -> Path:
    """Write a file-level index of all generated artifacts in a run root."""

    destination = root / "artifact_index.csv"
    rows = []
    for file_path in run_files if run_files is not None else _iter_run_files(root):
        relative = file_path.relative_to(root)
        rows.append(
            {
                "section": _section_name_for_path(root, file_path),
                "relative_path": str(relative).replace("\\", "/"),
                "filename": file_path.name,
                "extension": file_path.suffix.lower(),
                "size_bytes": file_path.stat().st_size,
            }
        )
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["section", "relative_path", "filename", "extension", "size_bytes"])
        writer.writeheader()
        writer.writerows(rows)
    return destination


def _combined_output_rows(root: Path, run_files: Sequence[Path] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_path in run_files if run_files is not None else _iter_run_files(root):
        if file_path.name == "all_outputs.csv":
            continue
        relative = file_path.relative_to(root)
        section = _section_name_for_path(root, file_path)
        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            with file_path.open("r", newline="", encoding="utf-8-sig") as handle:
                for index, row in enumerate(csv.DictReader(handle)):
                    rows.append(
                        {
                            "section": section,
                            "source_file": str(relative).replace("\\", "/"),
                            "source_type": "csv_row",
                            "record_index": index,
                            "payload_json": json.dumps(dict(row), sort_keys=True),
                            "text_value": "",
                        }
                    )
            continue
        if suffix == ".json":
            payload = json.loads(file_path.read_text(encoding="utf-8-sig"))
            if isinstance(payload, list):
                iterable = payload
            elif isinstance(payload, dict):
                iterable = [payload]
            else:
                iterable = [payload]
            for index, item in enumerate(iterable):
                rows.append(
                    {
                        "section": section,
                        "source_file": str(relative).replace("\\", "/"),
                        "source_type": "json",
                        "record_index": index,
                        "payload_json": json.dumps(item, sort_keys=True),
                        "text_value": "",
                    }
                )
            continue
        if suffix == ".txt":
            for index, line in enumerate(file_path.read_text(encoding="utf-8-sig").splitlines()):
                rows.append(
                    {
                        "section": section,
                        "source_file": str(relative).replace("\\", "/"),
                        "source_type": "text_line",
                        "record_index": index,
                        "payload_json": "",
                        "text_value": line,
                    }
                )
            continue
        rows.append(
            {
                "section": section,
                "source_file": str(relative).replace("\\", "/"),
                "source_type": "artifact",
                "record_index": 0,
                "payload_json": "",
                "text_value": f"Binary or non-tabular artifact: {file_path.name}",
            }
        )
    return rows


def write_combined_outputs_csv(root: Path, run_files: Sequence[Path] | None = None) -> Path:
    """Write a run-level aggregate CSV spanning all generated outputs."""

    destination = root / "all_outputs.csv"
    rows = _combined_output_rows(root, run_files)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["section", "source_file", "source_type", "record_index", "payload_json", "text_value"],
        )
        writer.writeheader()
        writer.writerows(rows)
    return destination


@dataclass
class ArtifactRun:
    """A single workflow execution rooted under ``output/runs/<run_id>``."""

    root: Path
    run_id: str
    requested_mode: str
    sections: dict[str, Path] = field(default_factory=dict)

    def section_dir(self, name: str) -> Path:
        key = sanitize_filename(name)
        directory = ensure_directory(self.root / key)
        self.sections[key] = directory
        return directory

    def register_section(self, name: str, path: str | Path) -> Path:
        key = sanitize_filename(name)
        directory = ensure_directory(path)
        self.sections[key] = directory
        return directory

    def reports_dir(self) -> Path:
        return self.section_dir(REPORTS_DIRNAME)

    def write_manifest(
        self,
        *,
        status: str,
        summary: Mapping[str, Any] | None = None,
        config_paths: Mapping[str, Any] | None = None,
    ) -> Path:
        payload = {
            "run_id": self.run_id,
            "requested_mode": self.requested_mode,
            "status": status,
            "root": str(self.root),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "sections": {name: str(path) for name, path in sorted(self.sections.items())},
            "summary": dict(summary or {}),
            "config_paths": dict(config_paths or {}),
        }
        manifest_path = write_json(self.root / "manifest.json", payload)
        run_files = _iter_run_files(self.root)
        combined_path = write_combined_outputs_csv(self.root, run_files)
        index_path = write_artifact_index_csv(self.root, [*run_files, combined_path])
        latest_run_path = write_json(
            self.root.parent.parent / "latest_run.json",
            {
                "run_id": self.run_id,
                "requested_mode": self.requested_mode,
                "root": str(self.root),
                "manifest_path": str(manifest_path),
            },
        )
        LOGGER.info(
            "Wrote manifest bundle for run '%s' with %d tracked artifact(s): manifest=%s combined=%s index=%s latest=%s",
            self.run_id,
            len(run_files),
            manifest_path,
            combined_path,
            index_path,
            latest_run_path,
        )
        return manifest_path


def create_artifact_run(output_root: str | Path | None, requested_mode: str) -> ArtifactRun:
    """Create a timestamped artifact root for a workflow execution."""

    base_root = ensure_directory(Path(output_root) if output_root is not None else OUTPUT_ROOT)
    runs_root = ensure_directory(base_root / RUNS_DIRNAME)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"{timestamp}_{sanitize_filename(requested_mode)}"
    run_root = ensure_directory(runs_root / run_id)
    LOGGER.info("Initialized artifact root '%s'.", run_root)
    return ArtifactRun(root=run_root, run_id=run_id, requested_mode=requested_mode)
