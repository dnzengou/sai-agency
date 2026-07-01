"""Structured logging via structlog.

Emits JSON in production (machine-parseable, ship-to-anywhere) and a coloured
console renderer for local dev. Idempotent: safe to call multiple times.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_CONFIGURED = False


def configure_logging(level: str = "INFO", json_output: bool = True) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    # Operational logs go to stderr so stdout stays a clean, parseable result
    # channel for CLIs / CI / evo-metaclaw pipelines.
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=numeric_level)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_output:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
