"""Opinionated, production-ready pipelines pre-wired from ``agentx.azure``'s
service wrappers — the "Spring Boot for Azure AI" layer. Instead of composing
``AzurePipeline`` steps by hand, pick the shape that matches your workload:

    from agentx.azure.templates import AIOpsPipeline

    pipeline = AIOpsPipeline(name="claims-ai", storage="claims", queue="claim-queue")
    pipeline.run()  # Blob -> Service Bus -> (your worker) -> Cosmos -> Monitor, wired + logged

Every template is a thin, inspectable composition of the same wrappers used
directly in ``agentx.azure`` — nothing here is magic, it's just the wiring a
team would otherwise hand-roll for every project.
"""
from __future__ import annotations

from .aiops import AIOpsPipeline
from .chatbot import ChatbotPipeline
from .document_ai import DocumentAIPipeline
from .mlops import MLOpsPipeline
from .rag import RAGPipeline

__all__ = [
    "AIOpsPipeline",
    "MLOpsPipeline",
    "RAGPipeline",
    "ChatbotPipeline",
    "DocumentAIPipeline",
]
