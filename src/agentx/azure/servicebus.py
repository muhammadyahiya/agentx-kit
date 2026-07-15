"""Azure Service Bus queue wrapper: send + a retry/DLQ-aware consumer loop.

Design mirrors the doc's target DX —

    queue = ServiceBusQueue("invoice")

    @queue.consumer
    def process(data):
        return ai.extract(data)

    queue.listen()  # receive -> handler -> complete, or retry -> dead-letter

— everything else (structured logging, per-message retry, dead-lettering after
``max_delivery_attempts``, correlation IDs) is automatic, matching the
"receive / retry / logging / telemetry / DLQ / metrics" pipeline from the spec.
"""
from __future__ import annotations

import json
from typing import Any, Callable, TypeVar

from ._logging import azure_logger, get_correlation_id, log_operation
from ._retry import retry_kwargs
from .config import AzureSettings, get_azure_settings
from .credentials import AzureCredentialError, get_default_credential

logger = azure_logger("servicebus")

F = TypeVar("F", bound=Callable[[Any], Any])


class ServiceBusQueue:
    """A single Service Bus queue: JSON-friendly ``send`` + a consumer decorator.

    Auth: an explicit ``connection_string`` (or ``AZURE_SERVICEBUS_CONNECTION_STRING``)
    is tried first; otherwise ``namespace``/``AZURE_SERVICEBUS_NAMESPACE`` +
    Managed Identity (``DefaultAzureCredential``) is used, matching every other
    wrapper in this package.
    """

    def __init__(
        self,
        queue: str,
        connection_string: str | None = None,
        namespace: str | None = None,
        credential: Any = None,
        settings: AzureSettings | None = None,
        max_delivery_attempts: int = 3,
    ):
        try:
            from azure.servicebus import ServiceBusClient
        except ImportError as exc:
            raise RuntimeError(
                "azure-servicebus is not installed. Run "
                "`pip install 'agentx-kit[azure-servicebus]'`."
            ) from exc

        settings = settings or get_azure_settings()
        self.queue = queue
        self.max_delivery_attempts = max_delivery_attempts
        self._handler: Callable[[Any], Any] | None = None

        conn_str = connection_string or settings.servicebus_connection_string
        ns = namespace or settings.servicebus_namespace

        if conn_str:
            self._client = ServiceBusClient.from_connection_string(conn_str, **retry_kwargs(settings))
        elif ns:
            cred = credential or get_default_credential(settings)
            fqns = ns if ns.endswith(".servicebus.windows.net") else f"{ns}.servicebus.windows.net"
            self._client = ServiceBusClient(fully_qualified_namespace=fqns, credential=cred, **retry_kwargs(settings))
        else:
            raise AzureCredentialError(
                "No Service Bus connection configured — set connection_string/namespace "
                "or AZURE_SERVICEBUS_CONNECTION_STRING/AZURE_SERVICEBUS_NAMESPACE."
            )

    @log_operation("servicebus")
    def send(self, data: dict | str) -> None:
        """Send one message. Dicts are JSON-encoded; strings are sent as-is."""
        from azure.servicebus import ServiceBusMessage

        body = json.dumps(data) if isinstance(data, dict) else data
        with self._client.get_queue_sender(queue_name=self.queue) as sender:
            sender.send_messages(ServiceBusMessage(body, correlation_id=get_correlation_id()))

    def consumer(self, fn: F) -> F:
        """Register ``fn`` as the message handler. Returns ``fn`` unchanged so it
        stays directly callable/testable; wire it up by calling :meth:`listen`."""
        self._handler = fn
        return fn

    @log_operation("servicebus")
    def listen(self, max_messages: int | None = None, max_wait_time: float = 5.0) -> int:
        """Receive messages and run the registered handler on each.

        On handler success: ``complete_message`` (removes it from the queue).
        On handler failure: retried up to ``max_delivery_attempts`` local
        attempts (via ``abandon_message``, which makes it immediately
        redeliverable); once the message's own delivery count exceeds that,
        it's explicitly ``dead_letter_message``'d rather than left to loop
        forever. Returns the number of messages processed (completed or
        dead-lettered).
        """
        if self._handler is None:
            raise RuntimeError("No consumer registered — use @queue.consumer before listen().")

        processed = 0
        with self._client.get_queue_receiver(queue_name=self.queue, max_wait_time=max_wait_time) as receiver:
            for message in receiver:
                if max_messages is not None and processed >= max_messages:
                    break
                payload: Any = str(message)
                try:
                    payload = json.loads(str(message))
                except (TypeError, ValueError):
                    pass
                try:
                    self._handler(payload)
                except Exception as exc:  # noqa: BLE001 - routed to retry/DLQ, not swallowed silently
                    delivery_count = getattr(message, "delivery_count", 0) or 0
                    if delivery_count >= self.max_delivery_attempts:
                        logger.error(
                            "Dead-lettering message after %d delivery attempts: %s",
                            delivery_count, exc,
                            extra={"service": "servicebus", "operation": "listen",
                                   "correlation_id": get_correlation_id(), "outcome": "dead_letter"},
                        )
                        receiver.dead_letter_message(message, reason=str(exc)[:4096])
                    else:
                        logger.warning(
                            "Abandoning message (attempt %d/%d): %s",
                            delivery_count, self.max_delivery_attempts, exc,
                            extra={"service": "servicebus", "operation": "listen",
                                   "correlation_id": get_correlation_id(), "outcome": "abandon"},
                        )
                        receiver.abandon_message(message)
                else:
                    receiver.complete_message(message)
                processed += 1
        return processed
