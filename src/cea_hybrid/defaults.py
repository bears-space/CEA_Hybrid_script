"""JSON-backed default configuration used by the legacy CEA workflow."""

from __future__ import annotations

from copy import deepcopy

from project_data import load_project_defaults


def get_default_raw_config():
    """Return a deep copy of the root-level default CEA configuration."""
    return deepcopy(load_project_defaults()["cea"])
