"""Shared workflow runtime preparation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.artifacts import ArtifactRun, create_artifact_run
from src.cfd import merge_cfd_config
from src.config import (
    build_design_config,
    load_design_config,
    normalize_cfd_config,
    normalize_hydraulic_validation_config,
    normalize_nozzle_offdesign_config,
    normalize_structural_config,
    normalize_testing_config,
    normalize_thermal_config,
)
from src.hydraulic_validation import merge_hydraulic_validation_config
from src.io_utils import load_json
from src.nozzle_offdesign import merge_nozzle_offdesign_config
from src.structural import merge_structural_config
from src.testing import merge_testing_config
from src.thermal import merge_thermal_config


@dataclass(frozen=True)
class WorkflowContext:
    mode: str
    run: ArtifactRun
    config_paths: dict[str, Any]
    cea_config_path: str | None
    cea_override: Mapping[str, Any] | None
    study_config: dict[str, Any] | None = None
    hydraulic_config: dict[str, Any] | None = None
    structural_config: dict[str, Any] | None = None
    thermal_config: dict[str, Any] | None = None
    nozzle_offdesign_config: dict[str, Any] | None = None
    cfd_config: dict[str, Any] | None = None
    testing_config: dict[str, Any] | None = None


def _load_override_payload(path: str | None, override: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if override is not None:
        return deepcopy(dict(override))
    if path:
        return load_json(path)
    return None


def prepare_workflow_context(
    *,
    mode: str,
    config_path: str | None = None,
    cea_config_path: str | None = None,
    hydraulic_config_path: str | None = None,
    structural_config_path: str | None = None,
    thermal_config_path: str | None = None,
    nozzle_offdesign_config_path: str | None = None,
    cfd_config_path: str | None = None,
    testing_config_path: str | None = None,
    output_root: str | Path,
    design_override: Mapping[str, Any] | None = None,
    cea_override: Mapping[str, Any] | None = None,
    hydraulic_override: Mapping[str, Any] | None = None,
    structural_override: Mapping[str, Any] | None = None,
    thermal_override: Mapping[str, Any] | None = None,
    nozzle_offdesign_override: Mapping[str, Any] | None = None,
    cfd_override: Mapping[str, Any] | None = None,
    testing_override: Mapping[str, Any] | None = None,
) -> WorkflowContext:
    """Create the run root and all merged/normalized config payloads for a workflow."""

    run = create_artifact_run(output_root, mode)
    config_paths = {
        "design_config": "inline" if design_override is not None else config_path,
        "cea_config": "inline" if cea_override is not None else cea_config_path,
        "hydraulic_validation_config": "inline" if hydraulic_override is not None else hydraulic_config_path,
        "structural_config": "inline" if structural_override is not None else structural_config_path,
        "thermal_config": "inline" if thermal_override is not None else thermal_config_path,
        "nozzle_offdesign_config": "inline" if nozzle_offdesign_override is not None else nozzle_offdesign_config_path,
        "cfd_config": "inline" if cfd_override is not None else cfd_config_path,
        "testing_config": "inline" if testing_override is not None else testing_config_path,
    }
    if mode == "cea":
        return WorkflowContext(
            mode=mode,
            run=run,
            config_paths=config_paths,
            cea_config_path=cea_config_path,
            cea_override=deepcopy(dict(cea_override)) if cea_override is not None else None,
        )

    study_config = (
        build_design_config(design_override)
        if design_override is not None
        else (load_design_config(config_path) if config_path else build_design_config())
    )
    hydraulic_override_payload = _load_override_payload(hydraulic_config_path, hydraulic_override)
    structural_override_payload = _load_override_payload(structural_config_path, structural_override)
    thermal_override_payload = _load_override_payload(thermal_config_path, thermal_override)
    nozzle_offdesign_override_payload = _load_override_payload(nozzle_offdesign_config_path, nozzle_offdesign_override)
    cfd_override_payload = _load_override_payload(cfd_config_path, cfd_override)
    testing_override_payload = _load_override_payload(testing_config_path, testing_override)

    hydraulic_config = normalize_hydraulic_validation_config(
        merge_hydraulic_validation_config(study_config, hydraulic_override_payload),
        study_config,
    )
    structural_config = normalize_structural_config(
        merge_structural_config(study_config, structural_override_payload),
        study_config,
    )
    thermal_config = normalize_thermal_config(
        merge_thermal_config(study_config, thermal_override_payload),
        study_config,
    )
    nozzle_offdesign_config = normalize_nozzle_offdesign_config(
        merge_nozzle_offdesign_config(study_config, nozzle_offdesign_override_payload),
        study_config,
    )
    cfd_config = normalize_cfd_config(
        merge_cfd_config(study_config, cfd_override_payload),
        study_config,
    )
    testing_config = normalize_testing_config(
        merge_testing_config(study_config, testing_override_payload),
        study_config,
    )
    study_config["hydraulic_validation"] = hydraulic_config
    study_config["structural"] = structural_config
    study_config["thermal"] = thermal_config
    study_config["nozzle_offdesign"] = nozzle_offdesign_config
    study_config["cfd"] = cfd_config
    study_config["testing"] = testing_config

    return WorkflowContext(
        mode=mode,
        run=run,
        config_paths=config_paths,
        cea_config_path=cea_config_path,
        cea_override=deepcopy(dict(cea_override)) if cea_override is not None else None,
        study_config=study_config,
        hydraulic_config=hydraulic_config,
        structural_config=structural_config,
        thermal_config=thermal_config,
        nozzle_offdesign_config=nozzle_offdesign_config,
        cfd_config=cfd_config,
        testing_config=testing_config,
    )
