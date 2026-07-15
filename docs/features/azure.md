# Azure AI platform (`agentx.azure`)

A production Azure infrastructure layer, in the same spirit as the enterprise
pack: instead of hand-rolling `azure-storage-blob` / `azure-servicebus` /
`azure-cosmos` boilerplate for every project, wire it in a few lines with
structured logging, correlation IDs, retries, and Managed Identity already
built in.

```python
from agentx.azure import AzurePipeline

pipeline = (
    AzurePipeline(name="document-processing")
    .blob_storage(container="documents")
    .service_bus(queue="document-queue")
    .container_app(image="processor:latest")
    .azure_ml(endpoint="invoice-model")
    .cosmosdb(database="documents")
)
pipeline.deploy()               # plan only — no Azure calls, no credentials needed
pipeline.deploy(execute=True)   # actually wire each step
```

Every `.xxx(...)` call just records a declarative step; nothing touches Azure
until `.deploy()` runs, and `.deploy()` defaults to a dry-run plan — the same
"plan before apply" pattern as Terraform. Install only what you use:

```bash
pip install "agentx-kit[azure-blob]"          # one service
pip install "agentx-kit[azure-platform]"      # everything below + pyyaml (for the CLI)
```

## Credentials

Every wrapper resolves auth the same way, in priority order:

1. An explicit `connection_string` (or `key`) argument.
2. The matching `AZURE_*_CONNECTION_STRING` / `AZURE_*_KEY` env var.
3. **Managed Identity** (`DefaultAzureCredential`) — the recommended
   production path: no secrets to store, rotate, or leak. Set
   `AZURE_CLIENT_ID` only for a user-assigned identity.

If nothing resolves, construction fails immediately with
`AzureCredentialError` rather than deferring the failure to the first network
call. `agentx azure init` writes a `.env.example` listing every var.

## Service wrappers

| Wrapper | Extra | Notes |
|---|---|---|
| `BlobStorageService` | `azure-blob` | upload/download/list/delete/exists |
| `ServiceBusQueue` | `azure-servicebus` | `send` + a `@queue.consumer` decorator; `listen()` completes on success, retries (`abandon`) up to `max_delivery_attempts`, then dead-letters |
| `CosmosService` | `azure-cosmos` | `upsert`/`get`/`query`/`delete`; auto-creates the database/container |
| `KeyVaultService` | `azure-keyvault` | `get_secret`/`set_secret` with an in-process TTL cache |
| `EventGridService` | `azure-eventgrid` | `publish(event_type, data)` as a `CloudEvent` |
| `ContainerAppService` | `azure-containerapp` | `generate_dockerfile`/`generate_manifest`/`write_manifests` (pure, no credentials) + `deploy`/`remove` (live, via `azure-mgmt-appcontainers`) |
| `AzureMLService` | `azure-ml` | `invoke` an online endpoint, `submit_job`, `register_model`, `deploy_model` |
| `setup_azure_monitor` / `emit_metric` | `azure-monitor` | Application Insights export via OpenTelemetry |

Every public method is decorated with structured logging: a
`correlation_id` (propagated across a whole pipeline run via
`agentx.azure.correlation_scope`), `service`, `operation`, and `duration_ms`
on every line, under the `agentx.azure.*` logger namespace — so
`agentx.setup_logging(format="json")` gives you the same CloudWatch/Datadog-
ready output for Azure calls as for everything else in agentx. Retries are
tuned once via `AGENTX_AZURE_RETRY_TOTAL` / `AGENTX_AZURE_RETRY_BACKOFF` and
passed to every client (`retry_total`/`retry_backoff_factor`).

`ContainerAppService`'s manifest generation (Dockerfile, KEDA scale rules
including a Service-Bus-queue-length rule, health probes, system-assigned
Managed Identity) needs no Azure SDK at all — it's pure Python, so you can
generate and inspect it without any credentials.

## Templates

Pre-wired, opinionated pipelines built from the same wrappers above:

```python
from agentx.azure.templates import AIOpsPipeline

pipeline = AIOpsPipeline(name="claims-ai", storage="claims", queue="claim-queue", workers=5, ai_endpoint="gpt4o")
pipeline.run()  # Service Bus -> (Azure OpenAI by default, or @pipeline.processor) -> Cosmos -> metric
```

| Template | Shape | Notes |
|---|---|---|
| `AIOpsPipeline` | Service Bus → processor (Azure OpenAI by default) → Cosmos → metric | `write_manifests()` for the worker's Container App; `@pipeline.processor` to override the default AI call |
| `MLOpsPipeline` | Blob (dataset) → `train()` (Azure ML job) → `register_model()` → `deploy()` → `monitor_drift()` | |
| `RAGPipeline` | Blob (docs) → `agentx.rag` chunk/embed/index → `deploy()` scaffolds a FastAPI+RAG project via `agentx new` + a Container App manifest | Azure AI Search as a vector-store backend isn't wired yet — FAISS/Chroma/keyword, same as `agentx.rag` |
| `ChatbotPipeline` | Cosmos-backed session history + Azure OpenAI | Redis isn't wired — cross-instance session sharing isn't needed for most single-Container-App deployments; add Azure Cache for Redis yourself if you need it |
| `DocumentAIPipeline` | `AIOpsPipeline` subclass; default processor calls Azure AI Document Intelligence instead of a chat model | `azure-documentai` extra |

## CLI

```bash
agentx azure init --name claims-ai              # write pipeline.yaml + .env.example
agentx azure create aiops --name claims-ai       # write a starter <name>_pipeline.py
agentx azure plan pipeline.yaml                  # print the steps, no Azure calls
agentx azure deploy pipeline.yaml                # plan only
agentx azure deploy pipeline.yaml --execute      # actually wire it up
agentx azure destroy <container-app-name>        # delete a Container App (confirms first)
```

`pipeline.yaml` maps directly onto `AzurePipeline` steps:

```yaml
pipeline:
  name: claims-ai
storage:
  blob: claims
queue:
  servicebus: claim-queue
worker:
  replicas: 5
ml:
  endpoint: invoice-model
database:
  cosmos: claimsdb
monitoring:
  appinsights: true
```

## Testing without a live subscription

Every wrapper's tests mock the underlying `azure-sdk-for-python` client at
its source (`unittest.mock.patch("azure.storage.blob.BlobServiceClient")`,
etc.) — no network calls, no live subscription required. `ContainerAppService`'s
manifest generation and `AzurePipeline.deploy()` (plan-only) need no mocking
at all. See `tests/test_azure_*.py`.
