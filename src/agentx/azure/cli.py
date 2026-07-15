"""``agentx azure`` — scaffold, plan, and deploy Azure AI pipelines from the CLI.

    agentx azure init                 # write pipeline.yaml + .env.example
    agentx azure create aiops         # write a starter <name>_pipeline.py
    agentx azure plan pipeline.yaml   # print the steps a config would wire
    agentx azure deploy pipeline.yaml # deploy (--execute for real; plan-only by default)
    agentx azure destroy <name>       # tear down a deployed Container App (confirms first)
"""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

azure_app = typer.Typer(help="Scaffold, plan, and deploy Azure AI pipelines.", no_args_is_help=True)
console = Console()

_TEMPLATES = {
    "aiops": ("AIOpsPipeline", "agentx.azure.templates", 'AIOpsPipeline(name="{name}", storage="{name}-storage", queue="{name}-queue")'),
    "mlops": ("MLOpsPipeline", "agentx.azure.templates", 'MLOpsPipeline(dataset="dataset.csv", experiment="{name}")'),
    "rag": ("RAGPipeline", "agentx.azure.templates", 'RAGPipeline(documents="docs/")'),
    "chatbot": ("ChatbotPipeline", "agentx.azure.templates", 'ChatbotPipeline(name="{name}")'),
    "document-ai": ("DocumentAIPipeline", "agentx.azure.templates", 'DocumentAIPipeline(name="{name}", storage="{name}-storage", queue="{name}-queue")'),
}

_ENV_EXAMPLE = """\
# Managed Identity is preferred — leave the rest blank in production and let
# DefaultAzureCredential authenticate via the deployed identity. Fill in a
# connection string / key per-service only for local dev.
AZURE_CLIENT_ID=

AZURE_STORAGE_CONNECTION_STRING=
AZURE_SERVICEBUS_CONNECTION_STRING=
AZURE_SERVICEBUS_NAMESPACE=
AZURE_COSMOS_CONNECTION_STRING=
AZURE_COSMOS_ENDPOINT=
AZURE_COSMOS_KEY=
AZURE_KEYVAULT_URL=
AZURE_EVENTGRID_TOPIC_ENDPOINT=
AZURE_EVENTGRID_TOPIC_KEY=
APPLICATIONINSIGHTS_CONNECTION_STRING=

AZURE_SUBSCRIPTION_ID=
AZURE_RESOURCE_GROUP=
AZURE_LOCATION=eastus
AZURE_ML_WORKSPACE_NAME=
"""

_PIPELINE_YAML_TEMPLATE = """\
pipeline:
  name: {name}
storage:
  blob: {name}-storage
queue:
  servicebus: {name}-queue
worker:
  replicas: 1
database:
  cosmos: {name}db
monitoring:
  appinsights: true
"""


@azure_app.command()
def init(
    name: str = typer.Option("my-pipeline", "--name", help="Pipeline name used in the generated files."),
    output: Path = typer.Option(Path("."), "--output", "-o", help="Directory to write pipeline.yaml + .env.example into."),
) -> None:
    """Write a starter pipeline.yaml + .env.example."""
    output.mkdir(parents=True, exist_ok=True)
    (output / "pipeline.yaml").write_text(_PIPELINE_YAML_TEMPLATE.format(name=name))
    (output / ".env.example").write_text(_ENV_EXAMPLE)
    console.print(f"[green]Wrote[/] {output / 'pipeline.yaml'} and {output / '.env.example'}")


@azure_app.command()
def create(
    template: str = typer.Argument(..., help=f"One of: {', '.join(_TEMPLATES)}"),
    name: str = typer.Option("my-pipeline", "--name", help="Pipeline/resource name."),
    output: Path = typer.Option(None, "--output", "-o", help="File to write (default: <name>_pipeline.py)."),
) -> None:
    """Write a starter Python file wiring up the chosen template."""
    if template not in _TEMPLATES:
        console.print(f"[red]Unknown template {template!r}.[/] Choose from: {', '.join(_TEMPLATES)}")
        raise typer.Exit(1)
    class_name, module, ctor = _TEMPLATES[template]
    target = output or Path(f"{name.replace('-', '_')}_pipeline.py")
    target.write_text(
        f'"""Starter {class_name} — fill in the pieces marked TODO."""\n'
        f"from {module} import {class_name}\n\n\n"
        f"pipeline = {ctor.format(name=name)}\n\n"
        "if __name__ == \"__main__\":\n"
        "    pass  # TODO: call the methods this template exposes (see docs/azure.md)\n"
    )
    console.print(f"[green]Wrote[/] {target}")


@azure_app.command()
def plan(config: Path = typer.Argument(..., help="Path to a pipeline.yaml file.")) -> None:
    """Print the steps a pipeline config would wire, without touching Azure."""
    from .yaml_config import load_pipeline

    pipeline = load_pipeline(config)
    table = Table(title=f"Plan: {pipeline.name}")
    table.add_column("step", style="cyan")
    table.add_column("config")
    for step in pipeline.plan():
        kind = step.pop("kind")
        table.add_row(kind, str(step))
    console.print(table)


@azure_app.command()
def deploy(
    config: Path = typer.Argument(..., help="Path to a pipeline.yaml file."),
    execute: bool = typer.Option(
        False, "--execute", help="Actually wire each step (requires azure-* extras + credentials). Default: plan only."
    ),
) -> None:
    """Deploy a pipeline from a YAML config (plan-only unless --execute)."""
    from .yaml_config import load_pipeline

    pipeline = load_pipeline(config)
    pipeline.deploy(execute=execute)
    mode = "executed" if execute else "planned (pass --execute to actually wire it up)"
    console.print(f"[green]Pipeline '{pipeline.name}' {mode}.[/]")


@azure_app.command()
def destroy(
    name: str = typer.Argument(..., help="Container App name to delete."),
    resource_group: str = typer.Option(None, "--resource-group", "-g"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Delete a deployed Container App. Irreversible — confirms before acting."""
    if not yes and not typer.confirm(f"Really delete Container App '{name}'? This cannot be undone."):
        raise typer.Abort()

    from .containerapp import ContainerAppService

    ContainerAppService(image="", resource_group=resource_group).remove(name)
    console.print(f"[green]Deleted[/] Container App '{name}'.")
