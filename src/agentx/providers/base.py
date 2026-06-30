"""Provider abstractions: ``ProviderSpec`` and shared helpers.

A ``ProviderSpec`` is pure metadata + two builder callables. Builders import
their provider SDK lazily so installing one extra never forces the others.
"""
from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from typing import Any, Callable


class ProviderError(RuntimeError):
    """Raised when a provider cannot be constructed (missing package / creds)."""


def require(module: str, extra: str) -> Any:
    """Import ``module`` or raise a helpful, actionable error naming the extra."""
    try:
        return importlib.import_module(module)
    except ImportError as exc:  # pragma: no cover - exercised via factory error path
        raise ProviderError(
            f"Missing dependency '{module}'. Install it with:\n"
            f"    uv pip install 'agentx-kit[{extra}]'\n"
            f"(or: pip install {module})"
        ) from exc


def warn_missing_env(spec: "ProviderSpec") -> list[str]:
    """Return the subset of a provider's env vars that are not set."""
    return [v for v in spec.env_vars if not os.getenv(v)]


# A builder takes (model, **kwargs) and returns a LangChain BaseChatModel.
ChatBuilder = Callable[..., Any]


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    extra: str                      # pip extra: agentx-kit[<extra>]
    packages: tuple[str, ...]       # importable module names the extra provides
    default_model: str
    env_vars: tuple[str, ...]       # standard credential env vars (informational)
    crewai_prefix: str              # LiteLLM/CrewAI model prefix, e.g. "openrouter/"
    build_chat: ChatBuilder         # () -> langchain BaseChatModel
    notes: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)
