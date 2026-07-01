"""Centralized logging configuration for agentx.

Call ``setup_logging()`` once at application startup to get structured,
consistently formatted log output across all agentx modules.

All agentx loggers live under the ``agentx.*`` namespace so a single
``logging.getLogger("agentx")`` call controls the entire library.

Two output formats are supported:
  * ``"text"`` (default) — human-readable timestamped lines for local dev.
  * ``"json"``           — one JSON object per line, ready for CloudWatch /
                           Datadog / ELK aggregation in production.
"""
from __future__ import annotations

import json
import logging
import logging.config
import sys
import time
import traceback
from typing import Any, Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogFormat = Literal["text", "json"]

_TEXT_FMT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

_configured = False


# Attributes on LogRecord that we don't want to emit as duplicate JSON fields.
_LOG_RECORD_BUILTIN_ATTRS: frozenset[str] = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName",
    "taskName",  # Python 3.12+
})


class JsonFormatter(logging.Formatter):
    """One-line JSON formatter suitable for CloudWatch / Datadog / ELK.

    Emits fields:
      timestamp, level, logger, message, module, funcName, line
      + exception (if any)
      + any custom fields passed via ``extra={"key": value}``.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)
            ) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            payload["exception"] = "".join(traceback.format_exception(*record.exc_info)).strip()
        # Include any structured extras (LogRecord.__dict__ minus builtins).
        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_BUILTIN_ATTRS or key.startswith("_"):
                continue
            try:
                json.dumps(value)  # ensure serialisable
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(
    level: LogLevel | str = "INFO",
    fmt: str = _TEXT_FMT,
    format: LogFormat = "text",
    handler: logging.Handler | None = None,
    force: bool = False,
) -> None:
    """Configure the agentx logger hierarchy.

    Safe to call multiple times — subsequent calls are no-ops unless
    ``force=True``. Does *not* touch the root Python logger so it does
    not interfere with the host application's logging setup.

    Args:
        level: Log level string ("DEBUG", "INFO", "WARNING", …). Invalid
            values raise ``ValueError`` — no silent fallback.
        fmt: Text-format string (only used when ``format="text"``).
        format: ``"text"`` for local dev, ``"json"`` for production
            structured logging.
        handler: Custom handler to attach. Defaults to stderr StreamHandler.
        force: Re-configure even if already set up.
    """
    global _configured

    level_str = level.upper() if isinstance(level, str) else "INFO"
    if level_str not in _VALID_LEVELS:
        raise ValueError(
            f"Invalid log level {level!r}; expected one of {sorted(_VALID_LEVELS)}"
        )
    if format not in ("text", "json"):
        raise ValueError(f"Invalid format {format!r}; expected 'text' or 'json'")
    level_int = getattr(logging, level_str)

    formatter: logging.Formatter
    if format == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(fmt, datefmt=_DATEFMT)

    root = logging.getLogger("agentx")

    if _configured and not force:
        for h in root.handlers:
            if h.formatter is None:
                h.setFormatter(formatter)
        root.setLevel(level_int)
        return

    if root.handlers and not force:
        for h in root.handlers:
            if h.formatter is None:
                h.setFormatter(formatter)
        root.setLevel(level_int)
        root.propagate = False
        _configured = True
        return

    # Fresh configuration
    for h in root.handlers[:]:
        root.removeHandler(h)

    h = handler or logging.StreamHandler(sys.stderr)
    h.setFormatter(formatter)
    root.addHandler(h)
    root.setLevel(level_int)
    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``agentx`` namespace.

    ``get_logger("foo")``  → ``agentx.foo``
    ``get_logger("")``     → ``agentx``
    ``get_logger("agentx.bar")`` → ``agentx.bar`` (unchanged)

    Never produces a trailing dot or escapes the ``agentx.*`` hierarchy.
    """
    if not name:
        return logging.getLogger("agentx")
    if name == "agentx" or name.startswith("agentx."):
        return logging.getLogger(name)
    return logging.getLogger(f"agentx.{name}")
