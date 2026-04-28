"""Shared workflow execution for CLI and UI entrypoints."""

from __future__ import annotations

import logging
from pathlib import Path
import time
from typing import Any, Mapping

from src.constants import OUTPUT_ROOT
from src.logging_utils import bind_logger, configure_logging
from src.workflows.cli import parse_args
from src.workflows.handlers import dispatch_workflow
from src.workflows.modes import resolve_mode_alias, summary_lines
from src.workflows.runtime import prepare_workflow_context

LOGGER = logging.getLogger(__name__)


def run_workflow(
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
    output_root: str | Path = OUTPUT_ROOT,
    design_override: Mapping[str, Any] | None = None,
    cea_override: Mapping[str, Any] | None = None,
    hydraulic_override: Mapping[str, Any] | None = None,
    structural_override: Mapping[str, Any] | None = None,
    thermal_override: Mapping[str, Any] | None = None,
    nozzle_offdesign_override: Mapping[str, Any] | None = None,
    cfd_override: Mapping[str, Any] | None = None,
    testing_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a workflow mode with shared config preparation and artifact handling."""

    configure_logging()
    resolved_mode = resolve_mode_alias(mode)
    start_time = time.perf_counter()
    logger = bind_logger(LOGGER, mode=resolved_mode)
    logger.info("Preparing workflow context.")
    context = prepare_workflow_context(
        mode=resolved_mode,
        config_path=config_path,
        cea_config_path=cea_config_path,
        hydraulic_config_path=hydraulic_config_path,
        structural_config_path=structural_config_path,
        thermal_config_path=thermal_config_path,
        nozzle_offdesign_config_path=nozzle_offdesign_config_path,
        cfd_config_path=cfd_config_path,
        testing_config_path=testing_config_path,
        output_root=output_root,
        design_override=design_override,
        cea_override=cea_override,
        hydraulic_override=hydraulic_override,
        structural_override=structural_override,
        thermal_override=thermal_override,
        nozzle_offdesign_override=nozzle_offdesign_override,
        cfd_override=cfd_override,
        testing_override=testing_override,
    )
    logger = bind_logger(LOGGER, mode=resolved_mode, run_id=context.run.run_id)
    logger.info("Workflow context prepared; dispatching handler for artifact root '%s'.", context.run.root)
    try:
        result = dispatch_workflow(context)
    except Exception:
        logger.exception("Workflow execution failed.")
        raise
    logger.info("Workflow execution completed in %.2fs.", time.perf_counter() - start_time)
    return result


def main() -> None:
    """CLI entrypoint."""

    args = parse_args()
    configure_logging(level=args.log_level)
    result = run_workflow(
        mode=args.mode,
        config_path=args.config,
        cea_config_path=args.cea_config,
        hydraulic_config_path=args.hydraulic_config,
        structural_config_path=args.structural_config,
        thermal_config_path=args.thermal_config,
        nozzle_offdesign_config_path=args.nozzle_offdesign_config,
        cfd_config_path=args.cfd_config,
        testing_config_path=args.testing_config,
        output_root=args.output_dir,
    )
    for line in summary_lines(result):
        print(line)


if __name__ == "__main__":
    main()
