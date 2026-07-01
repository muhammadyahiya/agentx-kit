"""Runtime configuration for the agentx library (pydantic-settings).

Reads from environment / a local ``.env``. Only generic, cross-provider knobs
live here; provider credentials are read by each provider's SDK from their own
standard env vars (see ``agentx.providers.registry``).
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Allow both Python field names AND env-var aliases as constructor kwargs.
        populate_by_name=True,
    )

    # Default provider/model used when none is passed explicitly.
    default_provider: str = Field(default="openai", alias="AGENTX_PROVIDER")
    default_model: str = Field(default="", alias="AGENTX_MODEL")
    temperature: float = Field(default=0.3, alias="AGENTX_TEMPERATURE", ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, alias="AGENTX_MAX_TOKENS", ge=1)
    request_timeout: int = Field(default=120, alias="AGENTX_REQUEST_TIMEOUT", ge=1)

    # Local backends.
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )

    # HuggingFace provider settings.
    hf_api_token: str | None = Field(
        default=None,
        alias="HF_TOKEN",
        description="HuggingFace API token for Inference API access.",
    )
    hf_endpoint_url: str | None = Field(
        default=None,
        alias="HF_ENDPOINT_URL",
        description="Custom HuggingFace Inference Endpoint URL (overrides repo_id).",
    )
    hf_default_model: str = Field(
        default="",
        alias="HF_DEFAULT_MODEL",
        description="Default HuggingFace model repo ID.",
    )

    # Embedding provider defaults (used by RAG pipeline auto-detection).
    default_embedding_provider: str = Field(
        default="",
        alias="AGENTX_EMBEDDING_PROVIDER",
        description="Default embedding provider (huggingface, openai, cohere, …).",
    )
    default_embedding_model: str = Field(
        default="",
        alias="AGENTX_EMBEDDING_MODEL",
        description="Default embedding model ID for the selected provider.",
    )

    # Security: opt-out of FAISS pickle-based deserialization when loading indexes.
    faiss_allow_dangerous_load: bool = Field(
        default=False,
        alias="AGENTX_FAISS_ALLOW_DANGEROUS_LOAD",
        description="Allow loading FAISS indexes (uses pickle — trust source only).",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    """Clear the ``get_settings()`` cache — re-reads env/.env on next call.

    Useful in tests that mutate environment variables between cases.
    """
    get_settings.cache_clear()
