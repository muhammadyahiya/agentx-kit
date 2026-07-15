"""Azure Event Grid publisher — key auth first, Managed Identity for AAD topics.

Event Grid *topics* (as opposed to Event Grid *namespaces* / custom AAD-secured
resources) are commonly authenticated with a topic access key rather than AAD,
so ``EventGridService`` prefers key auth (``AzureKeyCredential``) whenever a
key is available and only falls back to ``get_default_credential()``
(``DefaultAzureCredential``, the Managed Identity path) for custom topics that
have an AAD data-plane role configured instead.

``topic`` is a *logical* label — it becomes the ``source`` field on every
``CloudEvent`` this service publishes (e.g. ``"document-processing"``) and is
only used in log lines and event metadata. It is not an Azure resource. The
actual Azure resource being published to is ``topic_endpoint``, the topic's
HTTPS endpoint URL.

Every public method is wrapped in ``@log_operation("eventgrid")`` so calls
emit structured start/success/failure log lines (with ``correlation_id``,
``duration_ms``) via ``agentx.azure._logging`` — no bespoke logging here.
"""
from __future__ import annotations

from typing import Any

from ._logging import log_operation
from ._retry import retry_kwargs
from .config import AzureSettings, get_azure_settings
from .credentials import AzureCredentialError, get_default_credential


class EventGridService:
    """Thin, typed wrapper around ``azure.eventgrid.EventGridPublisherClient``.

    Resolves the publish target and auth in this order:
      1. ``topic_endpoint`` argument, else ``settings.eventgrid_topic_endpoint``
         (``AZURE_EVENTGRID_TOPIC_ENDPOINT``) — required, raises
         ``AzureCredentialError`` if neither is set.
      2. Auth: ``topic_key`` argument, else ``settings.eventgrid_topic_key``
         (``AZURE_EVENTGRID_TOPIC_KEY``) — key auth via ``AzureKeyCredential``.
      3. Otherwise ``credential`` argument, else ``get_default_credential(settings)``
         — the Managed Identity / AAD path for custom topics.
    """

    def __init__(
        self,
        topic: str,
        topic_endpoint: str | None = None,
        topic_key: str | None = None,
        credential: Any = None,
        settings: AzureSettings | None = None,
    ) -> None:
        try:
            from azure.core.credentials import AzureKeyCredential
            from azure.core.messaging import CloudEvent
            from azure.eventgrid import EventGridPublisherClient
        except ImportError as exc:
            raise RuntimeError(
                "azure-eventgrid is not installed. Run "
                "`pip install 'agentx-kit[azure-eventgrid]'`."
            ) from exc

        self._CloudEvent = CloudEvent
        settings = settings or get_azure_settings()

        self.topic = topic
        resolved_endpoint = topic_endpoint or settings.eventgrid_topic_endpoint
        if not resolved_endpoint:
            raise AzureCredentialError(
                "EventGridService needs a topic endpoint (topic_endpoint arg or "
                "AZURE_EVENTGRID_TOPIC_ENDPOINT) to know where to publish events."
            )

        resolved_key = topic_key or settings.eventgrid_topic_key
        if resolved_key:
            resolved_credential: Any = AzureKeyCredential(resolved_key)
        else:
            resolved_credential = credential or get_default_credential(settings)

        self._client = EventGridPublisherClient(
            resolved_endpoint, resolved_credential, **retry_kwargs(settings)
        )

    @log_operation("eventgrid")
    def publish(self, event_type: str, data: dict, subject: str = "agentx") -> None:
        """Publish a single ``CloudEvent`` of ``event_type`` carrying ``data``."""
        event = self._CloudEvent(source=self.topic, type=event_type, data=data, subject=subject)
        self._client.send([event])
