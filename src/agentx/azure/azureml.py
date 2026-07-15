"""Azure Machine Learning: invoke an online endpoint, register + deploy models.

``azure-ai-ml`` is the heaviest optional dependency in this package (pulls in
MLflow and friends transitively), so it's never imported at module import
time — only inside the methods that actually need it, and only when the
``agentx-kit[azure-ml]`` extra is installed.
"""
from __future__ import annotations

import json
from typing import Any

from ._logging import log_operation
from .config import AzureSettings, get_azure_settings
from .credentials import AzureCredentialError, get_default_credential


class AzureMLService:
    """Thin wrapper over ``azure.ai.ml.MLClient`` scoped to one online endpoint."""

    def __init__(
        self,
        endpoint: str,
        workspace_name: str | None = None,
        subscription_id: str | None = None,
        resource_group: str | None = None,
        credential: Any = None,
        settings: AzureSettings | None = None,
    ):
        try:
            from azure.ai.ml import MLClient
        except ImportError as exc:
            raise RuntimeError(
                "azure-ai-ml is not installed. Run `pip install 'agentx-kit[azure-ml]'`."
            ) from exc

        settings = settings or get_azure_settings()
        self.endpoint = endpoint
        subscription_id = subscription_id or settings.subscription_id
        resource_group = resource_group or settings.resource_group
        workspace_name = workspace_name or settings.ml_workspace_name
        if not (subscription_id and resource_group and workspace_name):
            raise AzureCredentialError(
                "AzureMLService requires subscription_id, resource_group, and "
                "workspace_name (or AZURE_SUBSCRIPTION_ID / AZURE_RESOURCE_GROUP / "
                "AZURE_ML_WORKSPACE_NAME)."
            )

        cred = credential or get_default_credential(settings)
        self._client = MLClient(
            credential=cred,
            subscription_id=subscription_id,
            resource_group_name=resource_group,
            workspace_name=workspace_name,
        )

    @log_operation("azureml")
    def invoke(self, payload: dict[str, Any], deployment_name: str | None = None) -> Any:
        """Call the online endpoint with a JSON-serializable payload; returns the parsed JSON response."""
        raw = self._client.online_endpoints.invoke(
            endpoint_name=self.endpoint,
            deployment_name=deployment_name,
            input_data=json.dumps(payload),
        )
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return raw

    @log_operation("azureml")
    def submit_job(
        self,
        code: str,
        command: str,
        compute: str,
        environment: str = "azureml://registries/azureml/environments/sklearn-1.5/labels/latest",
        experiment_name: str | None = None,
        inputs: dict[str, Any] | None = None,
        instance_count: int = 1,
    ) -> Any:
        """Submit a training job: ``code`` is the local script directory, ``command``
        the shell command to run inside it (e.g. ``"python train.py --data ${{inputs.data}}"``)."""
        from azure.ai.ml import command as command_job

        job = command_job(
            code=code,
            command=command,
            environment=environment,
            compute=compute,
            experiment_name=experiment_name,
            inputs=inputs,
            instance_count=instance_count,
        )
        return self._client.jobs.create_or_update(job)

    @log_operation("azureml")
    def register_model(self, name: str, path: str, version: str | None = None) -> Any:
        """Register a model asset from a local path (or URI) under ``name``."""
        from azure.ai.ml.entities import Model

        model = Model(name=name, path=path, version=version)
        return self._client.models.create_or_update(model)

    @log_operation("azureml")
    def deploy_model(
        self,
        name: str,
        model: str,
        instance_type: str = "Standard_DS3_v2",
        instance_count: int = 1,
    ) -> Any:
        """Create/update an online deployment named ``name`` on this endpoint, running ``model``
        (a registered model reference, e.g. ``"invoice-model:3"``)."""
        from azure.ai.ml.entities import ManagedOnlineDeployment

        deployment = ManagedOnlineDeployment(
            name=name,
            endpoint_name=self.endpoint,
            model=model,
            instance_type=instance_type,
            instance_count=instance_count,
        )
        poller = self._client.online_deployments.begin_create_or_update(deployment)
        return poller.result()
