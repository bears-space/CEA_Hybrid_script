"""CLI entrypoint for the refactored workflow runner."""

from src.workflows import main, parse_args, resolve_mode_alias, run_workflow, summary_lines

__all__ = ["main", "parse_args", "resolve_mode_alias", "run_workflow", "summary_lines"]
