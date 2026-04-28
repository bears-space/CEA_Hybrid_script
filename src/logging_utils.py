"""Shared logging helpers for CLI and UI entrypoints."""

from __future__ import annotations

import logging
import sys
import threading
from typing import Any, TextIO

_LOGGING_LOCK = threading.Lock()
_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class ContextAdapter(logging.LoggerAdapter):
    """Prefix log messages with stable key/value context."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if not self.extra:
            return msg, kwargs
        context = " ".join(f"{key}={value}" for key, value in sorted(self.extra.items()) if value is not None)
        return (f"[{context}] {msg}" if context else msg), kwargs


def _normalize_level(level: int | str | None) -> int:
    if isinstance(level, int):
        return level
    if level is None:
        return logging.INFO
    candidate = getattr(logging, str(level).strip().upper(), None)
    return candidate if isinstance(candidate, int) else logging.INFO


def configure_logging(
    *,
    level: int | str | None = None,
    stream: TextIO | None = None,
    force: bool = False,
) -> logging.Logger:
    """Configure the root logger once and keep later calls idempotent."""

    resolved_level = _normalize_level(level)
    with _LOGGING_LOCK:
        root_logger = logging.getLogger()
        if force or not root_logger.handlers:
            handler = logging.StreamHandler(stream or sys.stderr)
            handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
            root_logger.handlers.clear()
            root_logger.addHandler(handler)
        root_logger.setLevel(resolved_level)
        return root_logger


def bind_logger(logger: logging.Logger, **context: Any) -> ContextAdapter:
    """Bind stable context values onto a logger."""

    return ContextAdapter(logger, {key: value for key, value in context.items() if value is not None})
