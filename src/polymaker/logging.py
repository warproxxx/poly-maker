"""structlog configuration: human console in dev, JSON to file in prod."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import structlog


def configure(
    *,
    level: str = "INFO",
    json_file: Path | None = None,
    console: bool = True,
) -> None:
    """Set up structlog + stdlib logging once at process start."""
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    if console:
        ch = logging.StreamHandler(sys.stderr)
        ch.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
                ]
            )
        )
        root.addHandler(ch)

    if json_file is not None:
        json_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(json_file)
        fh.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.JSONRenderer(),
                ]
            )
        )
        root.addHandler(fh)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
