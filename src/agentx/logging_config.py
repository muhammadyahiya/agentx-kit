"""Centralized logging configuration for agentx.

Call ``setup_logging()`` once at application startup to get structured,
consistently formatted log output across all agentx modules.

All agentx loggers live under the ``agentx.*`` namespace so a single
``logging.getLogger("agentx")`` call controls the entire library.
"""
from __future__ import annotations

import logging
import logging.config
import sys
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_FMT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

_configured = False


def setup_logging(
    level: LogLevel | str = "INFO",
    fmt: str = _FMT,
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
        fmt: Log format string. Defaults to timestamped module-aware format.
        handler: Custom handler to attach. Defaults to stderr StreamHandler.
        force: Re-configure even if already set up.
    """
    global _configured

    level_str = level.upper() if isinstance(level, str) else "INFO"
    if level_str not in _VALID_LEVELS:
        raise ValueError(
            f"Invalid log level {level!r}; expected one of {sorted(_VALID_LEVELS)}"
        )
    level_int = getattr(logging, level_str)

    root = logging.getLogger("agentx")

    if _configured and not force:
        # Apply level/formatter to existing handlers so pre-existing plain
        # handlers get our formatter (fixes T1-Bug9).
        formatter = logging.Formatter(fmt, datefmt=_DATEFMT)
        for h in root.handlers:
            if h.formatter is None:
                h.setFormatter(formatter)
        root.setLevel(level_int)
        return

    if root.handlers and not force:
        formatter = logging.Formatter(fmt, datefmt=_DATEFMT)
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
    h.setFormatter(logging.Formatter(fmt, datefmt=_DATEFMT))
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
