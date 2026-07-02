"""Curated model catalogs per provider.

A best-effort list of commonly-used, currently-available model IDs for each
provider, so UIs (the dashboard, the wizard) can offer a dropdown instead of a
blank text box. This is intentionally NOT exhaustive and WILL drift over time —
every consumer keeps a free-text escape hatch so any model ID can still be used
(new releases, private HF repos, Azure deployment names, pulled Ollama tags).

Model IDs are grouped most-capable/most-recent first. Where a provider is
Anthropic, the Claude IDs are the current generation (Opus 4.8, Sonnet 5,
Haiku 4.5, Fable 5) verified against the claude-api reference.
"""
from __future__ import annotations

from .registry import get_spec

# Keyed by canonical provider id (see registry.canonical_ids()).
MODELS: dict[str, list[str]] = {
    "openai": [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "o3",
        "o3-mini",
        "o4-mini",
    ],
    "azure": [
        # Azure uses *deployment* names — these are common base model names to
        # start from; the actual value is whatever you named the deployment.
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4.1",
        "gpt-35-turbo",
    ],
    "openrouter": [
        "openai/gpt-4o-mini",
        "anthropic/claude-sonnet-4.6",
        "google/gemini-2.0-flash-001",
        "meta-llama/llama-3.3-70b-instruct",
        "mistralai/mistral-large",
        "deepseek/deepseek-r1",
        "qwen/qwen-2.5-72b-instruct",
    ],
    "anthropic": [
        # Current generation (claude-api reference). Opus 4.8 is most capable.
        "claude-opus-4-8",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "claude-opus-4-7",
        "claude-sonnet-5",
        "claude-fable-5",
    ],
    "gemini": [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ],
    "vertexai": [
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ],
    "bedrock": [
        "anthropic.claude-3-5-sonnet-20240620-v1:0",
        "anthropic.claude-3-5-haiku-20241022-v1:0",
        "meta.llama3-1-70b-instruct-v1:0",
        "mistral.mistral-large-2407-v1:0",
        "amazon.nova-pro-v1:0",
        "amazon.nova-lite-v1:0",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
        "qwen-2.5-32b",
        "deepseek-r1-distill-llama-70b",
    ],
    "ollama": [
        "llama3.2",
        "llama3.1",
        "llama3.3",
        "qwen2.5",
        "mistral",
        "gemma2",
        "phi3",
        "codellama",
        "deepseek-r1",
    ],
    "huggingface": [
        "HuggingFaceH4/zephyr-7b-beta",
        "meta-llama/Llama-3.1-8B-Instruct",
        "meta-llama/Llama-3.3-70B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "Qwen/Qwen2.5-7B-Instruct",
        "google/gemma-2-9b-it",
        "microsoft/Phi-3.5-mini-instruct",
    ],
    "cohere": [
        "command-r-plus",
        "command-r",
        "command-r7b-12-2024",
        "command",
    ],
    "mistral": [
        "mistral-large-latest",
        "mistral-small-latest",
        "open-mistral-nemo",
        "codestral-latest",
        "ministral-8b-latest",
    ],
}

# Curated embedding models per provider (for the RAG embedding selector).
EMBEDDING_MODELS: dict[str, list[str]] = {
    "huggingface": [
        "BAAI/bge-small-en-v1.5",
        "BAAI/bge-large-en-v1.5",
        "sentence-transformers/all-MiniLM-L6-v2",
        "intfloat/e5-large-v2",
    ],
    "openai": [
        "text-embedding-3-small",
        "text-embedding-3-large",
        "text-embedding-ada-002",
    ],
    "cohere": [
        "embed-english-v3.0",
        "embed-multilingual-v3.0",
    ],
    "google": [
        "models/text-embedding-004",
    ],
    "bedrock": [
        "amazon.titan-embed-text-v2:0",
        "cohere.embed-english-v3",
        "cohere.embed-multilingual-v3",
    ],
    "voyage": [
        "voyage-3",
        "voyage-3-lite",
        "voyage-code-3",
    ],
    "ollama": [
        "nomic-embed-text",
        "mxbai-embed-large",
    ],
}


def models_for(provider: str) -> list[str]:
    """Return curated model IDs for ``provider``.

    Falls back to ``[spec.default_model]`` when the provider has no catalog
    entry, so the caller always gets at least one option.
    """
    key = (provider or "").strip().lower()
    if key in MODELS:
        return list(MODELS[key])
    try:
        return [get_spec(key).default_model]
    except KeyError:
        return []


def embedding_models_for(provider: str) -> list[str]:
    """Return curated embedding model IDs for ``provider`` (may be empty)."""
    return list(EMBEDDING_MODELS.get((provider or "").strip().lower(), []))


def default_index(provider: str, default_model: str) -> int:
    """Index of ``default_model`` within ``models_for(provider)``, else 0."""
    opts = models_for(provider)
    try:
        return opts.index(default_model)
    except ValueError:
        return 0
