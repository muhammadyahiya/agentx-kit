"""MLOpsPipeline — Blob (dataset) -> Azure ML training job -> register ->
deploy -> drift monitoring, matching the spec's

    Blob -> Azure ML -> Training Job -> Register Model -> Deploy Endpoint -> Monitor Drift
"""
from __future__ import annotations

from typing import Any

from .._logging import azure_logger
from ..azureml import AzureMLService
from ..blob import BlobStorageService
from ..config import AzureSettings, get_azure_settings
from ..monitor import emit_metric

logger = azure_logger("templates.mlops")


class MLOpsPipeline:
    def __init__(
        self,
        dataset: str,
        experiment: str,
        compute: str = "cpu-cluster",
        storage_container: str = "mlops-datasets",
        workspace_name: str | None = None,
        subscription_id: str | None = None,
        resource_group: str | None = None,
        settings: AzureSettings | None = None,
        credential: Any = None,
    ):
        self.dataset = dataset
        self.experiment = experiment
        self.compute = compute
        self.storage_container = storage_container
        self.endpoint_name = f"{experiment}-endpoint"
        self._settings = settings or get_azure_settings()
        self._credential = credential
        self._workspace_name = workspace_name
        self._subscription_id = subscription_id
        self._resource_group = resource_group
        self._blob: BlobStorageService | None = None
        self._ml: AzureMLService | None = None
        self.last_job: Any = None
        self._model_version: str | None = None

    def _blob_service(self) -> BlobStorageService:
        if self._blob is None:
            self._blob = BlobStorageService(
                container=self.storage_container, settings=self._settings, credential=self._credential
            )
        return self._blob

    def _ml_service(self) -> AzureMLService:
        if self._ml is None:
            self._ml = AzureMLService(
                endpoint=self.endpoint_name,
                workspace_name=self._workspace_name,
                subscription_id=self._subscription_id,
                resource_group=self._resource_group,
                settings=self._settings,
                credential=self._credential,
            )
        return self._ml

    def upload_dataset(self, data: bytes) -> str:
        """Upload the training dataset to Blob Storage; returns its URL."""
        return self._blob_service().upload(self.dataset, data)

    def train(
        self,
        code: str,
        command: str,
        environment: str | None = None,
        instance_count: int = 1,
    ) -> Any:
        """Submit the training job to Azure ML on ``self.compute``. ``code`` is the local
        training script directory, ``command`` the shell command to run inside it."""
        kwargs: dict[str, Any] = {}
        if environment:
            kwargs["environment"] = environment
        self.last_job = self._ml_service().submit_job(
            code=code, command=command, compute=self.compute,
            experiment_name=self.experiment, instance_count=instance_count, **kwargs,
        )
        return self.last_job

    def register_model(self, path: str, version: str | None = None) -> Any:
        """Register the trained model artifact under ``self.experiment``."""
        self._model_version = version
        return self._ml_service().register_model(self.experiment, path=path, version=version)

    def deploy(self, instance_type: str = "Standard_DS3_v2", instance_count: int = 1) -> Any:
        """Deploy the registered model to ``self.endpoint_name``."""
        model_ref = f"{self.experiment}:{self._model_version}" if self._model_version else self.experiment
        result = self._ml_service().deploy_model(
            "default", model=model_ref, instance_type=instance_type, instance_count=instance_count,
        )
        emit_metric("mlops.model_deployed", 1, experiment=self.experiment)
        return result

    def monitor_drift(self, metric_name: str, value: float) -> None:
        """Record a drift/quality metric for this experiment (via Azure Monitor if configured)."""
        emit_metric(f"mlops.{metric_name}", value, experiment=self.experiment)
