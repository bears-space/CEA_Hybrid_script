"""JSON-backed default values for the blowdown model."""

from __future__ import annotations

from copy import deepcopy

from project_data import load_project_defaults


_BLOWDOWN_DEFAULTS = load_project_defaults()["cea"]["blowdown"]

DEFAULT_CONFIG = deepcopy(_BLOWDOWN_DEFAULTS)
PROJECT_DEFAULT_USABLE_OXIDIZER_FRACTION = float(_BLOWDOWN_DEFAULTS["tank"]["usable_oxidizer_fraction"])
PROJECT_DEFAULT_FUEL_USABLE_FRACTION = float(_BLOWDOWN_DEFAULTS["grain"]["fuel_usable_fraction"])
PROJECT_DEFAULT_INJECTOR_CD = float(_BLOWDOWN_DEFAULTS["injector"]["cd"])
PROJECT_DEFAULT_INJECTOR_HOLE_COUNT = int(_BLOWDOWN_DEFAULTS["injector"]["hole_count"])
PROJECT_DEFAULT_PORT_COUNT = int(_BLOWDOWN_DEFAULTS["grain"]["port_count"])
PROJECT_DEFAULT_BURN_TIME_S = float(_BLOWDOWN_DEFAULTS["simulation"]["burn_time_s"])
