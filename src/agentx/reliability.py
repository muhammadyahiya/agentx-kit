"""Reliability: provider fallbacks, retries, budgets, and rate limiting.

- ``build_resilient_chat`` wraps a primary model with retries and sequential
  fallbacks to other providers/models (à la pydantic-ai's FallbackModel +
  the 'circular fallback' pattern from production templates).
- ``UsageLimits`` + ``UsageTracker`` enforce per-run request/token/cost budgets
  to stop runaway agent loops (à la pydantic-ai ``UsageLimits``).
- ``RateLimiter`` throttles LLM calls to stay under provider rate limits
  (requests per minute + tokens per minute) using a token-bucket algorithm.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from .providers import get_chat_model

logger = logging.getLogger(__name__)


def build_resilient_chat(
    provider: str | None = None,
    model: str | None = None,
    fallbacks: list[tuple[str, str]] | None = None,
    retries: int = 2,
    **kwargs,
):
    """Return a chat model with retry + ordered provider/model fallbacks.

    ``fallbacks`` is a list of ``(provider, model)`` tried in order if the
    primary fails. Built on LangChain's ``.with_retry()`` / ``.with_fallbacks()``.
    """
    primary = get_chat_model(provider, model, **kwargs)
    if retries and retries > 1:
        primary = primary.with_retry(stop_after_attempt=retries, wait_exponential_jitter=True)
    if fallbacks:
        alts = []
        for fb_provider, fb_model in fallbacks:
            try:
                alt = get_chat_model(fb_provider, fb_model, **kwargs)
                alts.append(alt.with_retry(stop_after_attempt=retries, wait_exponential_jitter=True))
            except Exception as exc:  # noqa: BLE001 - a missing extra shouldn't kill the chain
                logger.warning("Skipping fallback %s/%s: %s", fb_provider, fb_model, exc)
        if alts:
            primary = primary.with_fallbacks(alts)
    return primary


# ──────────────────────────────────────────────────────────────────────────────
# Usage budgets
# ──────────────────────────────────────────────────────────────────────────────

class UsageLimitExceeded(RuntimeError):
    """Raised when a configured request/token/cost budget is exceeded."""


@dataclass
class UsageLimits:
    max_requests: int | None = None
    max_total_tokens: int | None = None
    max_cost_usd: float | None = None
    # USD per 1K tokens (total). Override per your provider/model pricing.
    price_per_1k_tokens: float = 0.0


@dataclass
class UsageTracker:
    """Accumulates usage and enforces ``UsageLimits``.

    Call :meth:`record` with token counts after each model call (or attach
    :meth:`as_callback` to LangChain). Raises ``UsageLimitExceeded`` on breach.
    """

    limits: UsageLimits = field(default_factory=UsageLimits)
    requests: int = 0
    total_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        return round(self.total_tokens / 1000.0 * self.limits.price_per_1k_tokens, 6)

    def record(self, tokens: int = 0) -> None:
        self.requests += 1
        self.total_tokens += max(0, int(tokens))
        self._enforce()

    def _enforce(self) -> None:
        lim = self.limits
        if lim.max_requests is not None and self.requests > lim.max_requests:
            raise UsageLimitExceeded(f"max_requests exceeded ({self.requests} > {lim.max_requests})")
        if lim.max_total_tokens is not None and self.total_tokens > lim.max_total_tokens:
            raise UsageLimitExceeded(f"max_total_tokens exceeded ({self.total_tokens} > {lim.max_total_tokens})")
        if lim.max_cost_usd is not None and self.cost_usd > lim.max_cost_usd:
            raise UsageLimitExceeded(f"max_cost_usd exceeded (${self.cost_usd} > ${lim.max_cost_usd})")

    def as_callback(self):
        """Return a LangChain callback handler that records token usage."""
        from langchain_core.callbacks import BaseCallbackHandler

        tracker = self

        class _UsageCallback(BaseCallbackHandler):
            def on_llm_end(self, response, **kwargs):  # noqa: ANN001
                tokens = 0
                try:
                    usage = (response.llm_output or {}).get("token_usage") or {}
                    tokens = usage.get("total_tokens", 0)
                    if not tokens:  # some providers attach usage to message metadata
                        for gen in getattr(response, "generations", []) or []:
                            for g in gen:
                                meta = getattr(getattr(g, "message", None), "usage_metadata", None)
                                if meta:
                                    tokens += meta.get("total_tokens", 0)
                except Exception:  # noqa: BLE001
                    tokens = 0
                tracker.record(tokens)

        return _UsageCallback()


# ──────────────────────────────────────────────────────────────────────────────
# Rate limiter (token-bucket)
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RateLimiter:
    """Thread-safe token-bucket rate limiter for LLM calls.

    Enforces two independent buckets:
      * ``requests_per_minute`` — throttles call frequency.
      * ``tokens_per_minute``  — throttles cumulative token consumption
                                 (call ``consume_tokens(n)`` after each response).

    Zero / None on either dimension disables that bucket.

    Usage::

        limiter = RateLimiter(requests_per_minute=60, tokens_per_minute=90000)

        limiter.acquire()               # blocks until a request slot is free
        response = model.invoke(prompt)
        limiter.consume_tokens(response.usage_metadata['total_tokens'])
    """

    requests_per_minute: int = 0     # 0 = disabled
    tokens_per_minute: int = 0       # 0 = disabled
    burst: int = 1                   # allow small burst of requests at t=0
    _request_tokens: float = field(default=0.0, init=False)
    _tpm_tokens: float = field(default=0.0, init=False)
    _last_refill: float = field(default_factory=time.monotonic, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self) -> None:
        self._request_tokens = float(self.burst) if self.requests_per_minute else 0.0
        self._tpm_tokens = float(self.tokens_per_minute) if self.tokens_per_minute else 0.0

    def _refill(self, now: float) -> None:
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        if self.requests_per_minute:
            self._request_tokens = min(
                float(self.requests_per_minute),
                self._request_tokens + elapsed * (self.requests_per_minute / 60.0),
            )
        if self.tokens_per_minute:
            self._tpm_tokens = min(
                float(self.tokens_per_minute),
                self._tpm_tokens + elapsed * (self.tokens_per_minute / 60.0),
            )
        self._last_refill = now

    def acquire(self, timeout: float = 60.0) -> None:
        """Block until one request slot is available.

        Raises ``TimeoutError`` after ``timeout`` seconds of waiting.
        """
        if not self.requests_per_minute:
            return
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                now = time.monotonic()
                self._refill(now)
                if self._request_tokens >= 1.0:
                    self._request_tokens -= 1.0
                    return
                # Compute how long until we accrue one token.
                need = 1.0 - self._request_tokens
                wait = need * (60.0 / self.requests_per_minute)
            if time.monotonic() + wait > deadline:
                raise TimeoutError(
                    f"RateLimiter.acquire timed out after {timeout}s (rpm={self.requests_per_minute})"
                )
            time.sleep(min(wait, 0.25))

    def consume_tokens(self, tokens: int, timeout: float = 60.0) -> None:
        """Deduct ``tokens`` from the tokens-per-minute bucket, waiting if empty.

        Call this after every LLM response with the ``total_tokens`` count.
        """
        if not self.tokens_per_minute or tokens <= 0:
            return
        deadline = time.monotonic() + timeout
        remaining = float(tokens)
        while remaining > 0:
            with self._lock:
                now = time.monotonic()
                self._refill(now)
                take = min(self._tpm_tokens, remaining)
                if take > 0:
                    self._tpm_tokens -= take
                    remaining -= take
                if remaining <= 0:
                    return
                wait = (remaining - self._tpm_tokens) * (60.0 / self.tokens_per_minute)
            if time.monotonic() + wait > deadline:
                raise TimeoutError(
                    f"RateLimiter.consume_tokens timed out after {timeout}s "
                    f"(tpm={self.tokens_per_minute}, remaining={int(remaining)})"
                )
            time.sleep(min(max(wait, 0.05), 0.25))

    def stats(self) -> dict:
        """Return current bucket levels (for observability / dashboards)."""
        with self._lock:
            self._refill(time.monotonic())
            return {
                "request_tokens_available": self._request_tokens,
                "tpm_tokens_available": self._tpm_tokens,
                "requests_per_minute": self.requests_per_minute,
                "tokens_per_minute": self.tokens_per_minute,
            }


def rate_limited_callback(limiter: RateLimiter):
    """Return a LangChain callback that consumes tokens from ``limiter``
    after every model response.

    Attach alongside ``UsageTracker.as_callback()`` on ``.invoke(..., callbacks=...)``.
    """
    from langchain_core.callbacks import BaseCallbackHandler

    class _RateLimitCallback(BaseCallbackHandler):
        def on_llm_start(self, *args, **kwargs):  # noqa: ANN001, ANN201
            limiter.acquire()

        def on_llm_end(self, response, **kwargs):  # noqa: ANN001, ANN201
            tokens = 0
            try:
                usage = (response.llm_output or {}).get("token_usage") or {}
                tokens = usage.get("total_tokens", 0)
                if not tokens:
                    for gen in getattr(response, "generations", []) or []:
                        for g in gen:
                            meta = getattr(getattr(g, "message", None), "usage_metadata", None)
                            if meta:
                                tokens += meta.get("total_tokens", 0)
            except Exception:  # noqa: BLE001
                tokens = 0
            limiter.consume_tokens(tokens)

    return _RateLimitCallback()
