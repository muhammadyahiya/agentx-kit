"""ChatbotPipeline — a thin composition for the spec's

    Azure OpenAI + Cosmos DB + Redis + Container Apps

shape: a conversational turn goes to Azure OpenAI, history persists in Cosmos
DB (keyed by ``session_id``). Redis (short-term session cache) is not wired
here — ``agentx.memory`` already provides an in-process/SQLite short-term
buffer that covers the same need without another Azure resource; swap in
Azure Cache for Redis only if you need cross-instance session sharing.
"""
from __future__ import annotations

from typing import Any

from .._logging import azure_logger
from ..config import AzureSettings, get_azure_settings
from ..cosmos import CosmosService

logger = azure_logger("templates.chatbot")


class ChatbotPipeline:
    def __init__(
        self,
        name: str,
        model: str | None = None,
        cosmos_database: str | None = None,
        settings: AzureSettings | None = None,
        credential: Any = None,
    ):
        self.name = name
        self.model = model
        self.cosmos_database = cosmos_database or f"{name}-chat-history"
        self._settings = settings or get_azure_settings()
        self._credential = credential
        self._cosmos: CosmosService | None = None
        self._llm: Any = None

    def _cosmos_service(self) -> CosmosService:
        if self._cosmos is None:
            self._cosmos = CosmosService(
                database=self.cosmos_database, container="sessions", partition_key="/session_id",
                settings=self._settings, credential=self._credential,
            )
        return self._cosmos

    def _llm_client(self) -> Any:
        if self._llm is None:
            from ...providers import get_chat_model

            self._llm = get_chat_model("azure", model=self.model)
        return self._llm

    def history(self, session_id: str) -> list[dict[str, str]]:
        doc = self._cosmos_service().get(session_id, partition_key=session_id)
        return doc["messages"] if doc else []

    def send(self, session_id: str, message: str) -> str:
        """Send one turn: append to Cosmos-backed history, call Azure OpenAI, persist the reply."""
        messages = self.history(session_id)
        messages.append({"role": "user", "content": message})
        response = self._llm_client().invoke(message)
        reply = getattr(response, "content", str(response))
        messages.append({"role": "assistant", "content": reply})
        self._cosmos_service().upsert({"id": session_id, "session_id": session_id, "messages": messages})
        return reply
