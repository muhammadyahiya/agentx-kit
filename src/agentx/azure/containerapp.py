"""Azure Container Apps: generate production manifests, optionally deploy live.

Two responsibilities kept deliberately separate:

1. **Manifest generation** (`generate_dockerfile` / `generate_manifest` /
   `write_manifests`) — pure Python, no Azure SDK, no credentials required.
   Produces a Dockerfile + an ARM-shaped Container App "template" (containers,
   resources, KEDA autoscale rules incl. a Service Bus queue-length scaler,
   health probes, managed identity) — the "Dockerfile / ACA YAML / KEDA rules /
   Managed Identity / health probes" list from the spec.
2. **Live deploy** (`deploy`) — an *optional* step that calls
   ``azure-mgmt-appcontainers`` to actually create/update the Container App
   from that same manifest. Requires ``subscription_id``/``resource_group``
   and a real credential, so it's the one operation in this module that can't
   be exercised without a live Azure subscription.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ._logging import log_operation
from ._retry import retry_kwargs
from .config import AzureSettings, get_azure_settings
from .credentials import AzureCredentialError, get_default_credential


class ContainerAppService:
    def __init__(
        self,
        image: str,
        cpu: float = 1.0,
        memory: str = "2Gi",
        min_replicas: int = 1,
        max_replicas: int = 10,
        autoscale: bool = True,
        queue_name: str | None = None,
        queue_length_threshold: int = 5,
        env: dict[str, str] | None = None,
        subscription_id: str | None = None,
        resource_group: str | None = None,
        credential: Any = None,
        settings: AzureSettings | None = None,
    ):
        self.image = image
        self.cpu = cpu
        self.memory = memory
        self.min_replicas = min_replicas
        self.max_replicas = max_replicas
        self.autoscale = autoscale
        self.queue_name = queue_name
        self.queue_length_threshold = queue_length_threshold
        self.env = env or {}
        self._settings = settings or get_azure_settings()
        self.subscription_id = subscription_id or self._settings.subscription_id
        self.resource_group = resource_group or self._settings.resource_group
        self._credential = credential

    # ---- manifest / IaC generation (no Azure SDK, no credentials) ----

    def generate_dockerfile(self, base_image: str = "python:3.12-slim") -> str:
        return (
            f"FROM {base_image}\n"
            "WORKDIR /app\n"
            "COPY requirements.txt .\n"
            "RUN pip install --no-cache-dir -r requirements.txt\n"
            "COPY . .\n"
            "HEALTHCHECK --interval=30s --timeout=5s CMD python -c "
            "\"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\"\n"
            "CMD [\"python\", \"main.py\"]\n"
        )

    def _scale_rules(self) -> list[dict[str, Any]]:
        if not self.autoscale:
            return []
        rules: list[dict[str, Any]] = [
            {"name": "http-scale", "http": {"metadata": {"concurrentRequests": "50"}}}
        ]
        if self.queue_name:
            rules.append({
                "name": "servicebus-queue-scale",
                "custom": {
                    "type": "azure-servicebus",
                    "metadata": {
                        "queueName": self.queue_name,
                        "messageCount": str(self.queue_length_threshold),
                    },
                },
            })
        return rules

    def generate_manifest(self, name: str) -> dict[str, Any]:
        """Return the Container App resource body (ARM/Bicep-shaped dict).

        Includes a system-assigned managed identity, liveness/readiness
        probes, and (when ``autoscale``) KEDA scale rules — a Service Bus
        queue-length rule when ``queue_name`` is set, plus an HTTP rule.
        """
        return {
            "name": name,
            "location": self._settings.location,
            "identity": {"type": "SystemAssigned"},
            "properties": {
                "configuration": {
                    "activeRevisionsMode": "Single",
                    "ingress": {"external": True, "targetPort": 8000},
                },
                "template": {
                    "containers": [{
                        "name": name,
                        "image": self.image,
                        "resources": {"cpu": self.cpu, "memory": self.memory},
                        "env": [{"name": k, "value": v} for k, v in self.env.items()],
                        "probes": [
                            {"type": "Liveness", "httpGet": {"path": "/health", "port": 8000}},
                            {"type": "Readiness", "httpGet": {"path": "/ready", "port": 8000}},
                        ],
                    }],
                    "scale": {
                        "minReplicas": self.min_replicas,
                        "maxReplicas": self.max_replicas,
                        "rules": self._scale_rules(),
                    },
                },
            },
        }

    def write_manifests(self, output_dir: str | Path, name: str) -> list[Path]:
        """Write ``Dockerfile`` and ``containerapp.json`` to ``output_dir``. Returns the paths written."""
        import json

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        dockerfile_path = out / "Dockerfile"
        manifest_path = out / "containerapp.json"
        dockerfile_path.write_text(self.generate_dockerfile())
        manifest_path.write_text(json.dumps(self.generate_manifest(name), indent=2))
        return [dockerfile_path, manifest_path]

    # ---- live deploy (requires a real Azure subscription) ----

    @log_operation("containerapp")
    def deploy(self, name: str, environment_id: str | None = None) -> Any:
        """Create/update this Container App via ``azure-mgmt-appcontainers``.

        Requires ``subscription_id`` + ``resource_group`` (constructor args or
        ``AZURE_SUBSCRIPTION_ID``/``AZURE_RESOURCE_GROUP``) and a Managed
        Environment ``environment_id`` (the ACA "environment" resource ID this
        app runs in — not created here, since it's normally provisioned once
        per team, not per-pipeline).
        """
        try:
            from azure.mgmt.appcontainers import ContainerAppsAPIClient
            from azure.mgmt.appcontainers.models import (
                Container,
                ContainerApp,
                ManagedServiceIdentity,
                Scale,
                Template,
            )
        except ImportError as exc:
            raise RuntimeError(
                "azure-mgmt-appcontainers is not installed. Run "
                "`pip install 'agentx-kit[azure-containerapp]'`."
            ) from exc

        if not self.subscription_id or not self.resource_group:
            raise AzureCredentialError(
                "Container App deploy requires subscription_id + resource_group "
                "(or AZURE_SUBSCRIPTION_ID / AZURE_RESOURCE_GROUP)."
            )

        credential = self._credential or get_default_credential(self._settings)
        client = ContainerAppsAPIClient(
            credential=credential, subscription_id=self.subscription_id, **retry_kwargs(self._settings)
        )
        manifest = self.generate_manifest(name)
        container_app = ContainerApp(
            location=manifest["location"],
            identity=ManagedServiceIdentity(type="SystemAssigned"),
            managed_environment_id=environment_id,
            template=Template(
                containers=[Container(
                    name=name, image=self.image,
                    resources={"cpu": self.cpu, "memory": self.memory},
                )],
                scale=Scale(min_replicas=self.min_replicas, max_replicas=self.max_replicas),
            ),
        )
        poller = client.container_apps.begin_create_or_update(
            resource_group_name=self.resource_group, container_app_name=name, container_app_envelope=container_app
        )
        return poller.result()

    @log_operation("containerapp")
    def remove(self, name: str) -> None:
        """Delete this Container App. Irreversible — callers (e.g. the ``agentx azure
        destroy`` CLI command) are expected to confirm with the user first."""
        try:
            from azure.mgmt.appcontainers import ContainerAppsAPIClient
        except ImportError as exc:
            raise RuntimeError(
                "azure-mgmt-appcontainers is not installed. Run "
                "`pip install 'agentx-kit[azure-containerapp]'`."
            ) from exc

        if not self.subscription_id or not self.resource_group:
            raise AzureCredentialError(
                "Container App teardown requires subscription_id + resource_group "
                "(or AZURE_SUBSCRIPTION_ID / AZURE_RESOURCE_GROUP)."
            )

        credential = self._credential or get_default_credential(self._settings)
        client = ContainerAppsAPIClient(
            credential=credential, subscription_id=self.subscription_id, **retry_kwargs(self._settings)
        )
        poller = client.container_apps.begin_delete(resource_group_name=self.resource_group, container_app_name=name)
        poller.result()
