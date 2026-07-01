"""The provider registry — every supported LLM backend in one place.

Each entry's ``build_chat`` returns a LangChain ``BaseChatModel``. Builders pull
generic defaults (temperature, timeout) from settings and accept ``**kwargs``
overrides; provider credentials come from each SDK's standard env vars.
"""
from __future__ import annotations

import os
from typing import Any

from ..config import get_settings
from .base import ProviderSpec, require


def _common(kwargs: dict, *, timeout_kw: str | None = "timeout") -> dict:
    """Merge settings-based defaults into caller-provided kwargs.

    Applies:
        temperature      — from AGENTX_TEMPERATURE
        <timeout_kw>     — from AGENTX_REQUEST_TIMEOUT (keyword name varies by
                           provider; pass ``timeout_kw=None`` to skip)
        max_tokens       — from AGENTX_MAX_TOKENS if set

    Caller-provided kwargs win (``setdefault``).
    """
    s = get_settings()
    kwargs.setdefault("temperature", s.temperature)
    if timeout_kw:
        kwargs.setdefault(timeout_kw, s.request_timeout)
    if s.max_tokens is not None:
        kwargs.setdefault("max_tokens", s.max_tokens)
    return kwargs


# --------------------------------------------------------------------------- #
# Builders (lazy imports inside each)
# --------------------------------------------------------------------------- #
def _build_openai(model: str | None = None, **kwargs: Any):
    mod = require("langchain_openai", "openai")
    return mod.ChatOpenAI(model=model or "gpt-4o-mini", **_common(kwargs))


def _build_azure(model: str | None = None, **kwargs: Any):
    mod = require("langchain_openai", "azure")
    kwargs.setdefault("api_version", os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01"))
    kwargs.setdefault("azure_endpoint", os.getenv("AZURE_OPENAI_ENDPOINT"))
    # On Azure, `model` is the *deployment* name.
    return mod.AzureChatOpenAI(azure_deployment=model or os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"), **_common(kwargs))


def _build_openrouter(model: str | None = None, **kwargs: Any):
    mod = require("langchain_openai", "openrouter")
    s = get_settings()
    kwargs.setdefault("base_url", s.openrouter_base_url)
    kwargs.setdefault("api_key", os.getenv("OPENROUTER_API_KEY"))
    return mod.ChatOpenAI(model=model or "openai/gpt-4o-mini", **_common(kwargs))


def _build_anthropic(model: str | None = None, **kwargs: Any):
    mod = require("langchain_anthropic", "anthropic")
    # ChatAnthropic uses ``default_request_timeout`` (not ``timeout``).
    return mod.ChatAnthropic(
        model=model or "claude-3-5-sonnet-latest",
        **_common(kwargs, timeout_kw="default_request_timeout"),
    )


def _build_gemini(model: str | None = None, **kwargs: Any):
    mod = require("langchain_google_genai", "google")
    # ChatGoogleGenerativeAI does not expose a top-level timeout kwarg.
    return mod.ChatGoogleGenerativeAI(
        model=model or "gemini-1.5-flash",
        **_common(kwargs, timeout_kw=None),
    )


def _build_vertex(model: str | None = None, **kwargs: Any):
    mod = require("langchain_google_vertexai", "vertex")
    kwargs.setdefault("project", os.getenv("GOOGLE_CLOUD_PROJECT"))
    kwargs.setdefault("location", os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"))
    # ChatVertexAI uses request_parallelism, not a request timeout kwarg.
    return mod.ChatVertexAI(
        model=model or "gemini-1.5-flash",
        **_common(kwargs, timeout_kw=None),
    )


def _build_bedrock(model: str | None = None, **kwargs: Any):
    mod = require("langchain_aws", "bedrock")
    kwargs.setdefault("region_name", os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1")))
    # Bedrock uses botocore config for timeouts, not a top-level kwarg.
    return mod.ChatBedrockConverse(
        model=model or "anthropic.claude-3-5-sonnet-20240620-v1:0",
        **_common(kwargs, timeout_kw=None),
    )


def _build_groq(model: str | None = None, **kwargs: Any):
    mod = require("langchain_groq", "groq")
    return mod.ChatGroq(model=model or "llama-3.3-70b-versatile", **_common(kwargs))


def _build_ollama(model: str | None = None, **kwargs: Any):
    mod = require("langchain_ollama", "ollama")
    kwargs.setdefault("base_url", get_settings().ollama_base_url)
    return mod.ChatOllama(model=model or "llama3.2", **_common(kwargs))


def _build_huggingface(model: str | None = None, **kwargs: Any):
    mod = require("langchain_huggingface", "huggingface")
    s = get_settings()
    api_key = (
        kwargs.pop("huggingfacehub_api_token", None)
        or os.getenv("HF_TOKEN")
        or os.getenv("HUGGINGFACE_API_KEY")
        or s.hf_api_token
    )
    model_id = model or s.hf_default_model or "HuggingFaceH4/zephyr-7b-beta"
    endpoint_url = kwargs.pop("endpoint_url", None) or s.hf_endpoint_url

    # Separate kwargs that belong to HuggingFaceEndpoint from those for ChatHuggingFace.
    endpoint_kwargs = _common(kwargs)

    if endpoint_url:
        llm = mod.HuggingFaceEndpoint(
            endpoint_url=endpoint_url,
            huggingfacehub_api_token=api_key,
            **endpoint_kwargs,
        )
    else:
        llm = mod.HuggingFaceEndpoint(
            repo_id=model_id,
            huggingfacehub_api_token=api_key,
            **endpoint_kwargs,
        )
    return mod.ChatHuggingFace(llm=llm)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
_REGISTRY: dict[str, ProviderSpec] = {}


def _register(spec: ProviderSpec) -> None:
    _REGISTRY[spec.id] = spec
    for alias in spec.aliases:
        _REGISTRY[alias] = spec


_register(ProviderSpec(
    id="openai", label="OpenAI", extra="openai", packages=("langchain_openai",),
    default_model="gpt-4o-mini", env_vars=("OPENAI_API_KEY",), crewai_prefix="openai/",
    build_chat=_build_openai,
))
_register(ProviderSpec(
    id="azure", label="Azure OpenAI", extra="azure", packages=("langchain_openai",),
    default_model="gpt-4o", env_vars=("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT"),
    crewai_prefix="azure/", build_chat=_build_azure, aliases=("azure_openai",),
    notes="`model` is your Azure *deployment* name; set AZURE_OPENAI_API_VERSION/ENDPOINT.",
))
_register(ProviderSpec(
    id="openrouter", label="OpenRouter", extra="openrouter", packages=("langchain_openai",),
    default_model="openai/gpt-4o-mini", env_vars=("OPENROUTER_API_KEY",),
    crewai_prefix="openrouter/", build_chat=_build_openrouter,
    notes="OpenAI-compatible gateway to 200+ models; model id like 'anthropic/claude-3.5-sonnet'.",
))
_register(ProviderSpec(
    id="anthropic", label="Anthropic (Claude)", extra="anthropic", packages=("langchain_anthropic",),
    default_model="claude-3-5-sonnet-latest", env_vars=("ANTHROPIC_API_KEY",),
    crewai_prefix="anthropic/", build_chat=_build_anthropic, aliases=("claude",),
))
_register(ProviderSpec(
    id="gemini", label="Google Gemini (AI Studio)", extra="google",
    packages=("langchain_google_genai",), default_model="gemini-1.5-flash",
    env_vars=("GOOGLE_API_KEY",), crewai_prefix="gemini/", build_chat=_build_gemini,
    aliases=("google", "google_genai"),
))
_register(ProviderSpec(
    id="vertexai", label="Google Vertex AI", extra="vertex",
    packages=("langchain_google_vertexai",), default_model="gemini-1.5-flash",
    env_vars=("GOOGLE_CLOUD_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS"),
    crewai_prefix="vertex_ai/", build_chat=_build_vertex, aliases=("vertex",),
    notes="Uses ADC / service-account; set GOOGLE_CLOUD_PROJECT and credentials.",
))
_register(ProviderSpec(
    id="bedrock", label="Amazon Bedrock", extra="bedrock", packages=("langchain_aws",),
    default_model="anthropic.claude-3-5-sonnet-20240620-v1:0",
    env_vars=("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"), crewai_prefix="bedrock/",
    build_chat=_build_bedrock, aliases=("aws",),
    notes="Uses standard AWS credential chain; set AWS_REGION.",
))
_register(ProviderSpec(
    id="groq", label="Groq", extra="groq", packages=("langchain_groq",),
    default_model="llama-3.3-70b-versatile", env_vars=("GROQ_API_KEY",),
    crewai_prefix="groq/", build_chat=_build_groq,
))
_register(ProviderSpec(
    id="ollama", label="Ollama (local)", extra="ollama", packages=("langchain_ollama",),
    default_model="llama3.2", env_vars=(), crewai_prefix="ollama/",
    build_chat=_build_ollama, notes="Runs locally; no API key. `ollama serve` + pull a model.",
))
_register(ProviderSpec(
    id="huggingface",
    label="HuggingFace",
    extra="huggingface",
    packages=("langchain_huggingface",),
    default_model="HuggingFaceH4/zephyr-7b-beta",
    env_vars=("HF_TOKEN",),
    crewai_prefix="huggingface/",
    build_chat=_build_huggingface,
    aliases=("hf",),
    notes=(
        "Set HF_TOKEN for the Inference API, or HF_ENDPOINT_URL for a dedicated "
        "Inference Endpoint. Omit both to run a local pipeline (requires GPU/CPU)."
    ),
))


def get_spec(provider: str) -> ProviderSpec:
    key = (provider or "").strip().lower()
    if key not in _REGISTRY:
        raise KeyError(
            f"Unknown provider '{provider}'. Known: {', '.join(sorted(canonical_ids()))}"
        )
    return _REGISTRY[key]


def canonical_ids() -> list[str]:
    """Distinct canonical provider ids (excludes aliases), in registration order."""
    seen: list[str] = []
    for spec in _REGISTRY.values():
        if spec.id not in seen:
            seen.append(spec.id)
    return seen


def all_specs() -> list[ProviderSpec]:
    return [_REGISTRY[i] for i in canonical_ids()]
