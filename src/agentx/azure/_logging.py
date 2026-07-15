"""Structured logging + correlation IDs for agentx.azure.

Reuses agentx's existing JSON/text logging (``agentx.logging_config``) rather
than standing up a second logging stack — every wrapper call gets a
``correlation_id`` (propagated via a ``ContextVar`` so it survives a whole
pipeline run across services) plus ``service``/``operation``/``duration_ms``
as structured ``extra`` fields.
"""
from __future__ import annotations

import contextvars
import functools
import time
import uuid
from typing import Any, Callable, TypeVar

from ..logging_config import get_logger

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "agentx_azure_correlation_id", default=None
)

F = TypeVar("F", bound=Callable[..., Any])


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def get_correlation_id() -> str:
    """Return the active correlation ID, minting one lazily if none is set."""
    cid = _correlation_id.get()
    if cid is None:
        cid = new_correlation_id()
        _correlation_id.set(cid)
    return cid


def set_correlation_id(cid: str | None) -> contextvars.Token:
    return _correlation_id.set(cid)


def reset_correlation_id(token: contextvars.Token) -> None:
    _correlation_id.reset(token)


class correlation_scope:
    """Context manager: run a block under a fixed (or freshly minted) correlation ID.

        with correlation_scope() as cid:
            pipeline.deploy()   # every wrapper log line in here shares `cid`
    """

    def __init__(self, correlation_id: str | None = None):
        self.correlation_id = correlation_id or new_correlation_id()
        self._token: contextvars.Token | None = None

    def __enter__(self) -> str:
        self._token = set_correlation_id(self.correlation_id)
        return self.correlation_id

    def __exit__(self, *exc_info: Any) -> None:
        if self._token is not None:
            reset_correlation_id(self._token)


def azure_logger(service: str):
    """Return the ``agentx.azure.<service>`` logger."""
    return get_logger(f"azure.{service}")


def log_operation(service: str) -> Callable[[F], F]:
    """Decorator: structured start/success/failure logging + duration_ms + correlation_id
    around a wrapper method. Never swallows exceptions — logs then re-raises.
    """
    logger = azure_logger(service)

    def deco(fn: F) -> F:
        op = fn.__name__

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cid = get_correlation_id()
            extra: dict[str, Any] = {"correlation_id": cid, "service": service, "operation": op}
            start = time.monotonic()
            logger.info("%s.%s started", service, op, extra=extra)
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - logged then re-raised, not swallowed
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                logger.error(
                    "%s.%s failed after %sms: %s",
                    service, op, duration_ms, exc,
                    extra={**extra, "duration_ms": duration_ms, "outcome": "error"},
                    exc_info=True,
                )
                raise
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.info(
                "%s.%s succeeded in %sms",
                service, op, duration_ms,
                extra={**extra, "duration_ms": duration_ms, "outcome": "success"},
            )
            return result

        return wrapper  # type: ignore[return-value]

    return deco
