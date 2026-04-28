"""Workflow execution helpers."""

from src.workflows.cli import parse_args
from src.workflows.modes import mode_definitions_payload, resolve_mode_alias, summary_lines


def run_workflow(*args, **kwargs):
    """Import and run the shared workflow entrypoint lazily."""

    from src.workflows.engine import run_workflow as engine_run_workflow

    return engine_run_workflow(*args, **kwargs)


def main() -> None:
    """Import and run the CLI entrypoint lazily."""

    from src.workflows.engine import main as engine_main

    engine_main()


__all__ = ["main", "mode_definitions_payload", "parse_args", "resolve_mode_alias", "run_workflow", "summary_lines"]
