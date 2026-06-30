"""Public factory functions for building LLM clients across frameworks."""
from __future__ import annotations

import logging
from typing import Any

from ..config import get_settings
from .base import ProviderError, ProviderSpec, warn_missing_env
from .registry import all_specs, get_spec

logger = logging.getLogger(__name__)


def list_providers() -> list[ProviderSpec]:
    """Return all registered provider specs (canonical, no aliases)."""
    return all_specs()


def get_chat_model(provider: str | None = None, model: str | None = None, **kwargs: Any):
    """Build a LangChain ``BaseChatModel`` for any supported provider.

    Args:
        provider: provider id (e.g. "openai", "bedrock", "openrouter"). Defaults
            to ``AGENTX_PROVIDER`` / settings.
        model: model id; falls back to the provider's default.
        **kwargs: passed through to the underlying chat class (temperature, etc.).
    """
    s = get_settings()
    provider = provider or s.default_provider
    spec = get_spec(provider)
    model = model or s.default_model or spec.default_model

    missing = warn_missing_env(spec)
    if missing:
        logger.warning(
            "Provider '%s' is missing env vars: %s. The call may fail to authenticate.",
            spec.id, ", ".join(missing),
        )
    return spec.build_chat(model, **kwargs)


def get_crewai_llm(provider: str | None = None, model: str | None = None, **kwargs: Any):
    """Build a CrewAI ``LLM`` for any supported provider.

    CrewAI routes through LiteLLM, so we map the provider to its LiteLLM prefix
    (e.g. ``openrouter/`` , ``bedrock/`` , ``gemini/``) and pass base_url/api_key
    where relevant. Requires ``agentx-kit[crewai]``.
    """
    s = get_settings()
    provider = provider or s.default_provider
    spec = get_spec(provider)
    model = model or s.default_model or spec.default_model

    try:
        from crewai import LLM  # type: ignore
    except ImportError as exc:
        raise ProviderError(
            "CrewAI is not installed. Install it with:\n"
            "    uv pip install 'agentx-kit[crewai]'"
        ) from exc

    # Avoid double-prefixing if the caller already passed e.g. "openrouter/...".
    litellm_model = model if "/" in model and model.startswith(spec.crewai_prefix) else f"{spec.crewai_prefix}{model}"

    params: dict[str, Any] = {"model": litellm_model, "temperature": kwargs.pop("temperature", s.temperature)}
    if spec.id == "openrouter":
        params["base_url"] = s.openrouter_base_url
    if spec.id == "ollama":
        params["base_url"] = s.ollama_base_url
    params.update(kwargs)
    return LLM(**params)
