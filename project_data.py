"""Shared cached loaders for root-level project JSON data files."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent
DEFAULTS_PATH = ROOT_DIR / "defaults.json"
CONSTANTS_PATH = ROOT_DIR / "constants.json"


@lru_cache(maxsize=1)
def load_project_defaults() -> dict[str, Any]:
    return json.loads(DEFAULTS_PATH.read_text(encoding="utf-8-sig"))


@lru_cache(maxsize=1)
def load_project_constants() -> dict[str, Any]:
    return json.loads(CONSTANTS_PATH.read_text(encoding="utf-8-sig"))
