"""Map a natural-language problem statement to a recommended ProjectSpec.

Pure and dependency-free so it's testable and usable without the MCP SDK. The
connector uses this to turn a single user prompt into a complete project.
"""
from __future__ import annotations

import re

_STOP = {
    "a", "an", "the", "for", "with", "that", "this", "and", "or", "to", "of", "in",
    "on", "is", "are", "be", "build", "create", "make", "want", "need", "should",
    "able", "can", "will", "agent", "agents", "ai", "app", "application", "using",
    "use", "my", "our", "me", "you", "it", "system", "assistant", "bot", "help",
}

_ROLE_MAP = [
    (("support", "ticket", "helpdesk", "customer"), "Customer Support Agent"),
    (("research", "literature", "analyze papers", "summarize papers"), "Research Agent"),
    (("code", "developer", "programming", "refactor", "review pull"), "Coding Assistant"),
    (("data", "analytics", "sql", "report", "dashboard"), "Data Analyst"),
    (("sales", "lead", "crm", "outreach"), "Sales Assistant"),
    (("legal", "contract", "compliance", "policy"), "Compliance Assistant"),
    (("medical", "clinical", "patient", "health"), "Clinical Assistant"),
    (("devops", "infrastructure", "kubernetes", "deploy"), "DevOps Assistant"),
]


def _has(text: str, *kw: str) -> bool:
    return any(k in text for k in kw)


def _slug_from(text: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 2]
    picked = words[:3] or ["agentx", "app"]
    return "-".join(picked)


def _role_for(text: str) -> str:
    for keys, role in _ROLE_MAP:
        if _has(text, *keys):
            return role
    return "Assistant"


def _infer_mcp_tools(text: str) -> list[str]:
    """Guess which built-in MCP server tools fit the problem statement.

    Falls back to all four (the scaffolder's default) when nothing matches, so
    the generated server is still useful out of the box.
    """
    from ..tools.mcp_server import AVAILABLE_MCP_TOOLS

    picked: list[str] = []
    if _has(text, "search the web", "web search", "google", "up-to-date", "current events", "news"):
        picked.append("web_search")
    if _has(text, "speak", "voice", "audio", "text-to-speech", "tts", "read aloud", "narrate"):
        picked.append("tts")
    if _has(text, "knowledge base", "documents", "docs", "manual", "faq", "search our", " kb", "research"):
        picked.append("knowledge_research")
    if _has(text, "database", "sql", "query", "records", "rows", "table"):
        picked.append("database")
    return picked or list(AVAILABLE_MCP_TOOLS)


def recommend_spec(problem_statement: str) -> dict:
    """Return a recommended spec dict + rationale for a problem statement."""
    text = (problem_statement or "").lower().strip()

    multi = _has(text, "multi-agent", "multi agent", "multiple agents", "team of",
                 "crew", "collaborat", "debate", "researcher and", "reviewer", "planner")
    framework = "crewai" if multi else "langgraph"

    rag = _has(text, "document", "knowledge", "docs", "rag", "retriev", "pdf",
               "manual", "faq", "knowledge base", " kb", "our data", "company data",
               "search through", "cite", "sources")
    memory = _has(text, "remember", "conversation history", "multi-turn", "multi turn",
                  "across sessions", "previous", "chat history", "follow-up", "follow up")
    mcp = _has(text, "mcp", "external tool", "integrate with", "third-party", "third party",
               "plugin", "connect to", "external api")
    mcp_tools = _infer_mcp_tools(text) if mcp else []
    skills = _has(text, "guideline", "standard", "compliance", "policy", "style guide",
                  "best practice", "framework method")
    serve = _has(text, "api", "endpoint", "serve", "rest", "http", "backend",
                 "microservice", "webhook", "chat ui", "web app")
    production = _has(text, "production", "enterprise", "scalable", "observability",
                      "monitor", "trace", "secure", "reliable", "deploy", "high traffic")
    coding = _has(text, "coding", "write code", "code generation", "programming task")
    cache = _has(text, "cache", "cost", "cheap", "latency", "high traffic", "high-traffic",
                 "fast response", "reduce cost", "save money", "repeated")

    features: list[str] = []
    if rag:
        features.append("rag")
    if memory:
        features.append("memory")
    if mcp:
        features.append("mcp")
    if skills:
        features.append("skills")
    if serve or production:
        features.append("serve")
    if cache or production:
        features.append("cache")
    if production:
        features += ["observability", "guardrails", "docker", "ci", "evals"]
    # de-dupe, stable order
    seen: list[str] = []
    for f in features:
        if f not in seen:
            seen.append(f)

    agents = 3 if framework == "crewai" else 1
    role = _role_for(text)
    goal = (problem_statement or "Help the user accomplish their task accurately.").strip()
    system_prompt = (
        f"You are a {role}. {goal} "
        "Be accurate and concise, use your tools/knowledge before guessing, "
        "cite sources when available, and ask for clarification when the request is ambiguous."
    )

    rationale = (
        f"Chose **{framework}** ({'multi-agent collaboration detected' if multi else 'single-agent task'}); "
        f"features: {', '.join(seen) or 'none'}. "
        f"{'RAG (knowledge grounding). ' if rag else ''}"
        f"{'Serving/API layer. ' if serve or production else ''}"
        f"{'Full enterprise pack (tracing/guardrails/docker/CI/evals). ' if production else ''}"
    ).strip()

    return {
        "name": _slug_from(text),
        "framework": framework,
        "provider": "openai",
        "model": "",
        "agents": agents,
        "role": role,
        "goal": goal[:300],
        "system_prompt": system_prompt[:600],
        "features": seen,
        "mcp_tools": mcp_tools,
        "rationale": rationale,
    }
