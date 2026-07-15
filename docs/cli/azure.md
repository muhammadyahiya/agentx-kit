# `agentx azure`

Scaffold, plan, and deploy [Azure AI pipelines](../features/azure.md).

```bash
agentx azure --help
```

Every command works with **zero** Azure SDK packages installed except
`deploy --execute` and `destroy`, which need the relevant `azure-*` extra
and credentials (Managed Identity or a connection string).

| Subcommand | Purpose |
|---|---|
| `agentx azure init` | Write a starter `pipeline.yaml` + `.env.example` |
| `agentx azure create <template>` | Write a starter `<name>_pipeline.py` for a template (`aiops`, `mlops`, `rag`, `chatbot`, `document-ai`) |
| `agentx azure plan <file>` | Print the steps a config would wire — no Azure calls |
| `agentx azure deploy <file>` | Deploy a pipeline (`--execute` to actually wire it up; plan-only by default) |
| `agentx azure destroy <name>` | Delete a Container App (confirms first; `--yes` to skip) |

## Examples

```bash
agentx azure init --name claims-ai
agentx azure plan pipeline.yaml
agentx azure deploy pipeline.yaml               # plan-only, safe to run anywhere
agentx azure deploy pipeline.yaml --execute      # requires azure-platform + credentials
agentx azure create aiops --name claims-ai       # -> claims_ai_pipeline.py
agentx azure destroy processor-app --resource-group rg-1
```

## `pipeline.yaml`

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

Each top-level section maps to one `AzurePipeline` step; omitted sections are
simply not added. See [`agentx.azure.yaml_config`](../features/azure.md) for
the full mapping.
