"""Multi-provider embedding configurations and factory (Pydantic-based).

Each embedding provider is a Pydantic model whose ``build()`` method returns a
LangChain ``Embeddings`` instance.  Use ``get_embeddings(config)`` as the
single entry point; pass ``None`` for automatic provider detection.

Supported providers
-------------------
huggingface  local sentence-transformers or HF Inference API / Endpoints
openai       OpenAI text-embedding-3-* / ada-002 models
azure        Azure OpenAI embedding deployments
cohere       Cohere embed-v3 models
google       Google Generative AI text-embedding-004
bedrock      AWS Bedrock Titan / Cohere embeddings
voyage       Voyage AI high-quality retrieval embeddings
ollama       Local Ollama models (no API key required)

Install extras
--------------
agentx-kit[huggingface]  — HuggingFace embeddings
agentx-kit[openai]       — OpenAI embeddings
agentx-kit[azure]        — Azure OpenAI embeddings
agentx-kit[cohere]       — Cohere embeddings
agentx-kit[google]       — Google embeddings
agentx-kit[bedrock]      — AWS Bedrock embeddings
agentx-kit[voyage]       — Voyage AI embeddings
agentx-kit[ollama]       — Ollama embeddings
"""
from __future__ import annotations

import logging
import os
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Base
# ──────────────────────────────────────────────────────────────────────────────

class EmbeddingConfig(BaseModel):
    """Base class for all embedding provider configurations.

    Subclass one provider config below and call ``.build()`` to get a
    LangChain ``Embeddings`` object, or pass the config to ``get_embeddings()``.
    """

    provider: str
    model: str

    model_config = {"extra": "allow"}

    def build(self):
        """Build and return a LangChain ``Embeddings`` instance."""
        raise NotImplementedError(f"{type(self).__name__}.build() not implemented")


# ──────────────────────────────────────────────────────────────────────────────
# HuggingFace
# ──────────────────────────────────────────────────────────────────────────────

class HuggingFaceEmbeddingConfig(EmbeddingConfig):
    """HuggingFace embeddings — local sentence-transformers or Inference API.

    Behaviour:
    * ``endpoint_url`` is set → ``HuggingFaceEndpointEmbeddings`` pointed at
      a dedicated Inference Endpoint.
    * ``api_key`` / ``HF_TOKEN`` env var is set (no endpoint_url) → Inference
      API for a public Hub model.
    * Neither set → local ``HuggingFaceEmbeddings`` via sentence-transformers
      (no network required after the first download).

    Recommended local models: ``BAAI/bge-small-en-v1.5``,
    ``sentence-transformers/all-MiniLM-L6-v2``.
    """

    provider: Literal["huggingface"] = "huggingface"
    model: str = "BAAI/bge-small-en-v1.5"
    api_key: str | None = Field(default=None, description="HF_TOKEN / HUGGINGFACE_API_KEY")
    endpoint_url: str | None = Field(
        default=None,
        description="Custom HuggingFace Inference Endpoint URL",
    )
    encode_kwargs: dict[str, Any] = Field(
        default_factory=lambda: {"normalize_embeddings": True},
        description="Passed to sentence-transformers encode() for local models",
    )

    @model_validator(mode="before")
    @classmethod
    def _resolve_api_key(cls, values: dict) -> dict:
        if not values.get("api_key"):
            values["api_key"] = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_KEY")
        return values

    def build(self):
        try:
            from langchain_huggingface import (  # type: ignore
                HuggingFaceEmbeddings,
                HuggingFaceEndpointEmbeddings,
            )
        except ImportError as exc:
            raise ImportError(
                "Install 'agentx-kit[huggingface]' to use HuggingFace embeddings:\n"
                "    pip install 'agentx-kit[huggingface]'"
            ) from exc

        if self.endpoint_url:
            logger.info(
                "Building HuggingFace Endpoint embeddings: endpoint=%s model=%s",
                self.endpoint_url, self.model,
            )
            return HuggingFaceEndpointEmbeddings(
                model=self.endpoint_url,
                huggingfacehub_api_token=self.api_key,
            )

        if self.api_key:
            logger.info(
                "Building HuggingFace Inference API embeddings: model=%s", self.model,
            )
            return HuggingFaceEndpointEmbeddings(
                model=self.model,
                huggingfacehub_api_token=self.api_key,
            )

        logger.info(
            "Building local HuggingFace embeddings (sentence-transformers): model=%s", self.model,
        )
        return HuggingFaceEmbeddings(
            model_name=self.model,
            encode_kwargs=self.encode_kwargs,
        )


# ──────────────────────────────────────────────────────────────────────────────
# OpenAI
# ──────────────────────────────────────────────────────────────────────────────

class OpenAIEmbeddingConfig(EmbeddingConfig):
    """OpenAI text-embedding-3-* or ada-002 embeddings.

    Reads ``OPENAI_API_KEY`` from environment if ``api_key`` is not set.
    """

    provider: Literal["openai"] = "openai"
    model: str = "text-embedding-3-small"
    api_key: str | None = Field(default=None)
    dimensions: int | None = Field(
        default=None,
        description="Output dimension (supported by text-embedding-3-* only)",
    )

    @model_validator(mode="before")
    @classmethod
    def _resolve_api_key(cls, values: dict) -> dict:
        if not values.get("api_key"):
            values["api_key"] = os.getenv("OPENAI_API_KEY")
        return values

    def build(self):
        try:
            from langchain_openai import OpenAIEmbeddings  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "Install 'agentx-kit[openai]' to use OpenAI embeddings."
            ) from exc

        logger.info("Building OpenAI embeddings: model=%s", self.model)
        kwargs: dict[str, Any] = {"model": self.model}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.dimensions is not None:
            kwargs["dimensions"] = self.dimensions
        return OpenAIEmbeddings(**kwargs)


# ──────────────────────────────────────────────────────────────────────────────
# Azure OpenAI
# ──────────────────────────────────────────────────────────────────────────────

class AzureOpenAIEmbeddingConfig(EmbeddingConfig):
    """Azure OpenAI embeddings via a deployment name.

    Reads ``AZURE_OPENAI_API_KEY``, ``AZURE_OPENAI_ENDPOINT``, and
    ``AZURE_OPENAI_EMBEDDING_DEPLOYMENT`` from environment when not supplied.
    """

    provider: Literal["azure"] = "azure"
    model: str = Field(default="", description="Azure embedding deployment name")
    api_key: str | None = None
    endpoint: str | None = None
    api_version: str = "2024-06-01"

    @model_validator(mode="before")
    @classmethod
    def _resolve_env(cls, values: dict) -> dict:
        if not values.get("api_key"):
            values["api_key"] = os.getenv("AZURE_OPENAI_API_KEY")
        if not values.get("endpoint"):
            values["endpoint"] = os.getenv("AZURE_OPENAI_ENDPOINT")
        if not values.get("model"):
            values["model"] = os.getenv(
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002"
            )
        return values

    def build(self):
        try:
            from langchain_openai import AzureOpenAIEmbeddings  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "Install 'agentx-kit[azure]' to use Azure OpenAI embeddings."
            ) from exc

        logger.info(
            "Building Azure OpenAI embeddings: deployment=%s endpoint=%s",
            self.model, self.endpoint,
        )
        return AzureOpenAIEmbeddings(
            azure_deployment=self.model,
            openai_api_key=self.api_key,
            azure_endpoint=self.endpoint,
            openai_api_version=self.api_version,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Cohere
# ──────────────────────────────────────────────────────────────────────────────

class CohereEmbeddingConfig(EmbeddingConfig):
    """Cohere embed-v3 multilingual / English embeddings.

    Reads ``COHERE_API_KEY`` from environment when not supplied.
    ``input_type`` should be ``"search_document"`` at index time and
    ``"search_query"`` at query time.
    """

    provider: Literal["cohere"] = "cohere"
    model: str = "embed-english-v3.0"
    api_key: str | None = None
    input_type: str = Field(
        default="search_document",
        description="'search_document' for indexing, 'search_query' for queries",
    )

    @model_validator(mode="before")
    @classmethod
    def _resolve_api_key(cls, values: dict) -> dict:
        if not values.get("api_key"):
            values["api_key"] = os.getenv("COHERE_API_KEY")
        return values

    def build(self):
        try:
            from langchain_cohere import CohereEmbeddings  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "Install 'agentx-kit[cohere]' to use Cohere embeddings."
            ) from exc

        logger.info(
            "Building Cohere embeddings: model=%s input_type=%s",
            self.model, self.input_type,
        )
        return CohereEmbeddings(
            model=self.model,
            cohere_api_key=self.api_key,
            input_type=self.input_type,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Google Generative AI
# ──────────────────────────────────────────────────────────────────────────────

class GoogleEmbeddingConfig(EmbeddingConfig):
    """Google Generative AI embeddings (text-embedding-004).

    Reads ``GOOGLE_API_KEY`` from environment when not supplied.
    ``task_type`` choices: ``retrieval_document``, ``retrieval_query``,
    ``semantic_similarity``, ``classification``, ``clustering``.
    """

    provider: Literal["google"] = "google"
    model: str = "models/text-embedding-004"
    api_key: str | None = None
    task_type: str = "retrieval_document"

    @model_validator(mode="before")
    @classmethod
    def _resolve_api_key(cls, values: dict) -> dict:
        if not values.get("api_key"):
            values["api_key"] = os.getenv("GOOGLE_API_KEY")
        return values

    def build(self):
        try:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "Install 'agentx-kit[google]' to use Google embeddings."
            ) from exc

        logger.info(
            "Building Google Generative AI embeddings: model=%s task_type=%s",
            self.model, self.task_type,
        )
        return GoogleGenerativeAIEmbeddings(
            model=self.model,
            google_api_key=self.api_key,
            task_type=self.task_type,
        )


# ──────────────────────────────────────────────────────────────────────────────
# AWS Bedrock
# ──────────────────────────────────────────────────────────────────────────────

class BedrockEmbeddingConfig(EmbeddingConfig):
    """AWS Bedrock Titan or Cohere embeddings.

    Uses the standard AWS credential chain (env vars, ~/.aws/credentials,
    IAM role).  Set ``AWS_REGION`` / ``AWS_DEFAULT_REGION`` for the region.

    Common model IDs:
    * ``amazon.titan-embed-text-v2:0``   (1536-dim, default)
    * ``cohere.embed-english-v3``
    * ``cohere.embed-multilingual-v3``
    """

    provider: Literal["bedrock"] = "bedrock"
    model: str = "amazon.titan-embed-text-v2:0"
    region: str = Field(default="us-east-1", description="AWS region")

    @model_validator(mode="before")
    @classmethod
    def _resolve_region(cls, values: dict) -> dict:
        if not values.get("region"):
            values["region"] = (
                os.getenv("AWS_REGION")
                or os.getenv("AWS_DEFAULT_REGION")
                or "us-east-1"
            )
        return values

    def build(self):
        try:
            from langchain_aws import BedrockEmbeddings  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "Install 'agentx-kit[bedrock]' to use Bedrock embeddings."
            ) from exc

        logger.info(
            "Building AWS Bedrock embeddings: model=%s region=%s",
            self.model, self.region,
        )
        return BedrockEmbeddings(model_id=self.model, region_name=self.region)


# ──────────────────────────────────────────────────────────────────────────────
# Voyage AI
# ──────────────────────────────────────────────────────────────────────────────

class VoyageEmbeddingConfig(EmbeddingConfig):
    """Voyage AI embeddings — high-quality semantic retrieval.

    Reads ``VOYAGE_API_KEY`` from environment when not supplied.

    Common models: ``voyage-3``, ``voyage-3-lite``,
    ``voyage-code-3``, ``voyage-finance-2``.
    ``input_type``: ``"document"`` for indexing, ``"query"`` for queries.
    """

    provider: Literal["voyage"] = "voyage"
    model: str = "voyage-3"
    api_key: str | None = None
    input_type: str | None = Field(
        default="document",
        description="'document' when indexing, 'query' when searching",
    )

    @model_validator(mode="before")
    @classmethod
    def _resolve_api_key(cls, values: dict) -> dict:
        if not values.get("api_key"):
            values["api_key"] = os.getenv("VOYAGE_API_KEY")
        return values

    def build(self):
        try:
            from langchain_voyageai import VoyageAIEmbeddings  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "Install 'agentx-kit[voyage]' to use Voyage AI embeddings."
            ) from exc

        logger.info("Building Voyage AI embeddings: model=%s", self.model)
        return VoyageAIEmbeddings(
            voyage_api_key=self.api_key,
            model=self.model,
            input_type=self.input_type,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Ollama
# ──────────────────────────────────────────────────────────────────────────────

class OllamaEmbeddingConfig(EmbeddingConfig):
    """Local Ollama embeddings — no API key required.

    Reads ``OLLAMA_BASE_URL`` from environment (default: ``http://localhost:11434``).
    Recommended model: ``nomic-embed-text``.
    """

    provider: Literal["ollama"] = "ollama"
    model: str = "nomic-embed-text"
    base_url: str = Field(default="http://localhost:11434")

    @model_validator(mode="before")
    @classmethod
    def _resolve_base_url(cls, values: dict) -> dict:
        if not values.get("base_url"):
            values["base_url"] = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return values

    def build(self):
        try:
            from langchain_ollama import OllamaEmbeddings  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "Install 'agentx-kit[ollama]' to use Ollama embeddings."
            ) from exc

        logger.info(
            "Building Ollama embeddings: model=%s base_url=%s",
            self.model, self.base_url,
        )
        return OllamaEmbeddings(model=self.model, base_url=self.base_url)


# ──────────────────────────────────────────────────────────────────────────────
# Discriminated union (for typed config dicts)
# ──────────────────────────────────────────────────────────────────────────────

AnyEmbeddingConfig = Annotated[
    Union[
        HuggingFaceEmbeddingConfig,
        OpenAIEmbeddingConfig,
        AzureOpenAIEmbeddingConfig,
        CohereEmbeddingConfig,
        GoogleEmbeddingConfig,
        BedrockEmbeddingConfig,
        VoyageEmbeddingConfig,
        OllamaEmbeddingConfig,
    ],
    Field(discriminator="provider"),
]


# ──────────────────────────────────────────────────────────────────────────────
# Name → config class registry (single source of truth — was duplicated in
# cli.py and pipeline.py before Sprint 1 refactor).
# ──────────────────────────────────────────────────────────────────────────────

_PROVIDER_CONFIG_MAP: dict[str, type[EmbeddingConfig]] = {
    "huggingface": HuggingFaceEmbeddingConfig,
    "hf": HuggingFaceEmbeddingConfig,
    "openai": OpenAIEmbeddingConfig,
    "azure": AzureOpenAIEmbeddingConfig,
    "cohere": CohereEmbeddingConfig,
    "google": GoogleEmbeddingConfig,
    "bedrock": BedrockEmbeddingConfig,
    "aws": BedrockEmbeddingConfig,
    "voyage": VoyageEmbeddingConfig,
    "ollama": OllamaEmbeddingConfig,
}


def embedding_config_from_name(
    name: str, model: str | None = None, **kwargs
) -> EmbeddingConfig | None:
    """Build an EmbeddingConfig from a short provider name.

    Returns ``None`` for unknown or empty names.  Callers should treat that as
    'no provider selected — use auto_embeddings() or keyword fallback'.

    Args:
        name: Provider slug (``"huggingface"``, ``"openai"``, …).
        model: Optional model override — passed as ``model=`` to the config.
        **kwargs: Additional keyword args forwarded to the config constructor.
    """
    key = (name or "").strip().lower()
    cls = _PROVIDER_CONFIG_MAP.get(key)
    if cls is None:
        return None
    if model:
        kwargs["model"] = model
    return cls(**kwargs)


def known_embedding_providers() -> list[str]:
    """Return the sorted list of canonical embedding provider names."""
    return sorted(set(_PROVIDER_CONFIG_MAP.keys()))


# ──────────────────────────────────────────────────────────────────────────────
# Public factory
# ──────────────────────────────────────────────────────────────────────────────

def get_embeddings(config: EmbeddingConfig | None = None):
    """Build a LangChain ``Embeddings`` instance from a config object.

    Args:
        config: An ``EmbeddingConfig`` subclass (e.g. ``HuggingFaceEmbeddingConfig``).
                Pass ``None`` to trigger automatic provider detection.

    Returns:
        A LangChain ``Embeddings`` instance, or ``None`` if no provider is
        available (triggers keyword-fallback mode in the RAG pipeline).

    Examples::

        # HuggingFace local (no API key)
        emb = get_embeddings(HuggingFaceEmbeddingConfig())

        # HuggingFace Inference API
        emb = get_embeddings(HuggingFaceEmbeddingConfig(
            model="BAAI/bge-large-en-v1.5",
            api_key="hf_...",
        ))

        # Cohere
        emb = get_embeddings(CohereEmbeddingConfig(model="embed-english-v3.0"))

        # Auto-detect
        emb = get_embeddings()
    """
    if config is None:
        return auto_embeddings()
    logger.debug("Building embeddings from config: provider=%s model=%s", config.provider, config.model)
    return config.build()


def auto_embeddings():
    """Auto-detect the best available embedding provider.

    Detection order (first available wins):

    1. HuggingFace local sentence-transformers — offline-capable, no API key.
    2. OpenAI — if ``OPENAI_API_KEY`` is set and package is installed.
    3. Ollama — if the package is installed (assumes ``ollama serve`` is running).
    4. ``None`` — triggers in-memory keyword retrieval in the RAG pipeline.
    """
    # 1. HuggingFace local (no API key, works offline after first model download)
    try:
        from langchain_huggingface import HuggingFaceEmbeddings  # type: ignore

        logger.info(
            "Auto-selected HuggingFace local embeddings (BAAI/bge-small-en-v1.5)"
        )
        return HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-en-v1.5",
            encode_kwargs={"normalize_embeddings": True},
        )
    except ImportError:
        pass

    # 2. OpenAI (requires API key)
    try:
        from langchain_openai import OpenAIEmbeddings  # type: ignore

        if os.getenv("OPENAI_API_KEY"):
            logger.info("Auto-selected OpenAI embeddings (text-embedding-3-small)")
            return OpenAIEmbeddings(model="text-embedding-3-small")
    except ImportError:
        pass

    # 3. Ollama (local, no key needed)
    try:
        from langchain_ollama import OllamaEmbeddings  # type: ignore

        logger.info("Auto-selected Ollama embeddings (nomic-embed-text)")
        return OllamaEmbeddings(model="nomic-embed-text")
    except ImportError:
        pass

    logger.warning(
        "No embedding provider available; RAG will use keyword retrieval. "
        "Install 'agentx-kit[huggingface]' for free local embeddings."
    )
    return None
