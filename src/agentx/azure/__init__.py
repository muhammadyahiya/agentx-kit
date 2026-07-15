"""``agentx.azure`` — a production Azure AI platform layer: fluent pipeline
builder + service wrappers (Blob, Service Bus, Cosmos DB, Key Vault, Event
Grid, Container Apps, Azure ML) + Azure Monitor tracing, all with structured
logging, correlation IDs, retries, and Managed-Identity-first credentials
baked in. Everything here is lazy and extras-gated — importing
``agentx.azure`` costs nothing until you construct a specific service.

    from agentx.azure import AzurePipeline

    pipeline = (
        AzurePipeline(name="document-processing")
        .blob_storage(container="documents")
        .service_bus(queue="document-queue")
        .cosmosdb(database="documents")
    )
    pipeline.deploy()  # plan only; deploy(execute=True) to actually wire it up

See ``agentx.azure.templates`` for higher-level, pre-wired pipelines (AIOps,
MLOps, RAG, …) built on top of these same primitives.
"""
from __future__ import annotations

from ._logging import correlation_scope, get_correlation_id
from .azureml import AzureMLService
from .blob import BlobStorageService
from .config import AzureSettings, get_azure_settings, reset_azure_settings
from .containerapp import ContainerAppService
from .cosmos import CosmosService
from .credentials import AzureCredentialError, get_default_credential
from .eventgrid import EventGridService
from .keyvault import KeyVaultService
from .monitor import emit_metric, setup_azure_monitor
from .pipeline import AzurePipeline, PipelineStep
from .servicebus import ServiceBusQueue

__all__ = [
    "AzurePipeline",
    "PipelineStep",
    "AzureSettings",
    "get_azure_settings",
    "reset_azure_settings",
    "AzureCredentialError",
    "get_default_credential",
    "correlation_scope",
    "get_correlation_id",
    # service wrappers
    "BlobStorageService",
    "ServiceBusQueue",
    "CosmosService",
    "KeyVaultService",
    "EventGridService",
    "ContainerAppService",
    "AzureMLService",
    "setup_azure_monitor",
    "emit_metric",
]
