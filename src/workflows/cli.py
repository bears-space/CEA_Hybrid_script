"""CLI helpers for the shared workflow entrypoints."""

from __future__ import annotations

import argparse

from src.constants import OUTPUT_ROOT


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the workflow runner."""

    parser = argparse.ArgumentParser(description="Hybrid rocket workflow entry point.")
    parser.add_argument("--mode", required=True, help="Workflow mode to execute.")
    parser.add_argument("--config", default=None, help="Optional path to a design-workflow override JSON config.")
    parser.add_argument("--cea-config", dest="cea_config", default=None, help="Optional path to a CEA override JSON config.")
    parser.add_argument(
        "--hydraulic-config",
        dest="hydraulic_config",
        default=None,
        help="Optional path to a hydraulic-validation override JSON config.",
    )
    parser.add_argument("--coldflow-config", dest="hydraulic_config", default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--structural-config",
        dest="structural_config",
        default=None,
        help="Optional path to a structural-sizing override JSON config.",
    )
    parser.add_argument(
        "--thermal-config",
        dest="thermal_config",
        default=None,
        help="Optional path to a thermal-sizing override JSON config.",
    )
    parser.add_argument(
        "--nozzle-offdesign-config",
        dest="nozzle_offdesign_config",
        default=None,
        help="Optional path to a nozzle off-design override JSON config.",
    )
    parser.add_argument(
        "--cfd-config",
        dest="cfd_config",
        default=None,
        help="Optional path to a CFD planning / ingest override JSON config.",
    )
    parser.add_argument(
        "--testing-config",
        dest="testing_config",
        default=None,
        help="Optional path to a testing and readiness override JSON config.",
    )
    parser.add_argument("--output-dir", default=str(OUTPUT_ROOT), help="Root output directory for generated artifacts.")
    return parser.parse_args()
