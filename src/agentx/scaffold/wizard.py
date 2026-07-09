"""Interactive wizard — collects a ``ProjectSpec`` one option at a time.

Uses ``questionary`` for arrow-key selection. Every prompt has a sensible
default so power users can blast through with Enter.
"""
from __future__ import annotations

import questionary

from ..providers import all_specs, get_spec
from .spec import AgentSpec, ProjectSpec, VectorStoreBackend

_FRAMEWORKS = [
    ("LangGraph (LangChain)", "langgraph"),
    ("CrewAI", "crewai"),
]
_AGENT_MODES = [
    ("Chat  — interactive REPL / API (default)", "chat"),
    ("Autonomous  — goal-directed agent that plans and acts independently", "autonomous"),
    ("Research  — multi-step web research with citations and report generation", "research"),
    ("Deep  — planning (todo-list), filesystem, sub-agent delegation, optional reflection", "deep"),
]
_VECTOR_STORES = [
    ("Chroma  — persistent, server-less, easy setup (default)", "chroma"),
    ("FAISS   — fast in-process ANN search, saves to .faiss/ folder", "faiss"),
    ("Memory  — in-memory keyword retrieval, no embeddings required", "memory"),
]
_EMBEDDING_PROVIDERS = [
    ("Auto-detect  — HuggingFace local → OpenAI → Ollama (recommended)", ""),
    ("HuggingFace  — local sentence-transformers, no API key needed", "huggingface"),
    ("OpenAI        — text-embedding-3-small (needs OPENAI_API_KEY)", "openai"),
    ("Cohere        — embed-english-v3.0 (needs COHERE_API_KEY)", "cohere"),
    ("Ollama        — nomic-embed-text, fully local", "ollama"),
    ("Google        — text-embedding-004 (needs GOOGLE_API_KEY)", "google"),
    ("Bedrock       — Titan embeddings (needs AWS credentials)", "bedrock"),
    ("Voyage AI     — voyage-3, high-quality retrieval (needs VOYAGE_API_KEY)", "voyage"),
]
_MEMORY = [
    ("None", "none"),
    ("Short-term (windowed buffer)", "short"),
    ("Long-term (persistent JSONL)", "long"),
    ("Both", "both"),
]
_MCP_TOOLS = [
    ("Web search  — DuckDuckGo search + safe URL fetch", "web_search"),
    ("Text-to-speech  — edge-tts / OpenAI / pyttsx3", "tts"),
    ("Knowledge research  — keyword search over ./knowledge docs", "knowledge_research"),
    ("Database  — read-only SQL over a local SQLite file", "database"),
]
_ORCHESTRATION = [
    (
        "Supervisor  — an LLM router decides which agent acts next (best for open-ended queries)",
        "supervisor",
    ),
    (
        "Sequential  — agents run in order: agent_1 → agent_2 → … (pipeline / research-then-write)",
        "sequential",
    ),
    (
        "Parallel    — all agents answer simultaneously; their replies are merged (best for independent sub-tasks)",
        "parallel",
    ),
]


def _select(message: str, choices: list[tuple[str, str]], default_value: str) -> str:
    options = [questionary.Choice(title=label, value=value) for label, value in choices]
    default = next((o for o in options if o.value == default_value), options[0])
    return questionary.select(message, choices=options, default=default).ask()


def run_wizard(name: str | None = None) -> ProjectSpec | None:
    """Run the interactive flow; returns a ProjectSpec, or None if cancelled."""
    questionary.print("🧬  AgentX — new project\n", style="bold fg:cyan")

    name = name or questionary.text("Project name:", default="my-agent").ask()
    if not name:
        return None

    framework = _select("Agent framework:", _FRAMEWORKS, "langgraph")
    if framework is None:
        return None

    # Agent mode
    agent_mode = _select("Agent mode:", _AGENT_MODES, "chat")
    if agent_mode is None:
        agent_mode = "chat"

    # Provider + model
    provider_choices = [
        (f"{s.label}  ·  needs: {', '.join(s.env_vars) or 'no key (local)'}", s.id)
        for s in all_specs()
    ]
    provider = _select("LLM provider:", provider_choices, "openai")
    if provider is None:
        return None
    pspec = get_spec(provider)
    model = questionary.text(
        f"Model id ({pspec.label}):", default=pspec.default_model
    ).ask() or pspec.default_model

    # Agents
    n_str = questionary.text("How many agents?", default="1").ask() or "1"
    try:
        n_agents = max(1, min(10, int(n_str)))
    except ValueError:
        n_agents = 1
    agents: list[AgentSpec] = []
    for i in range(n_agents):
        questionary.print(f"\nAgent {i + 1} of {n_agents}", style="bold")
        a_name = questionary.text("  name:", default=f"agent_{i + 1}" if n_agents > 1 else "assistant").ask()
        a_role = questionary.text("  role:", default="Helpful Assistant").ask()
        a_goal = questionary.text("  goal:", default="Help the user accomplish their task accurately.").ask()
        a_prompt = questionary.text(
            "  system prompt (optional — blank = auto from role/goal):", default="",
            multiline=True,
        ).ask()
        agents.append(AgentSpec(
            name=a_name or f"agent_{i + 1}",
            role=a_role or "Assistant",
            goal=a_goal or "Help the user.",
            system_prompt=(a_prompt or "").strip(),
        ))

    # Orchestration — only ask when there is more than one agent and framework is LangGraph
    orchestration = "supervisor"
    if n_agents > 1 and framework == "langgraph":
        questionary.print(
            "\nYou have multiple agents. How should they connect to the orchestrator?",
            style="bold fg:yellow",
        )
        orchestration = _select("Orchestration mode:", _ORCHESTRATION, "supervisor")
        if orchestration is None:
            orchestration = "supervisor"

    # Capabilities — one by one
    use_rag = questionary.confirm("Add a RAG module (knowledge base)?", default=False).ask()

    vector_store: VectorStoreBackend = "chroma"
    embedding_provider: str = ""
    if use_rag:
        questionary.print("\nRAG settings:", style="bold fg:cyan")
        vector_store = _select(
            "  Vector store backend:", _VECTOR_STORES, "chroma"
        ) or "chroma"
        embedding_provider = _select(
            "  Embedding provider:", _EMBEDDING_PROVIDERS, ""
        ) or ""
        questionary.print(
            "  Tip: upload documents later with:  agentx rag upload <file> --project ./",
            style="dim",
        )
    memory = _select("Agent memory:", _MEMORY, "none")
    use_mcp = questionary.confirm("Integrate MCP tools?", default=False).ask()
    mcp_tools: list[str] = []
    if use_mcp:
        mcp_tools = questionary.checkbox(
            "  Which built-in MCP tools should your own server expose?",
            choices=[questionary.Choice(title=label, value=value, checked=True) for label, value in _MCP_TOOLS],
        ).ask() or []
    use_skills = questionary.confirm("Add a skills registry?", default=False).ask()

    # Sub-agents / swarm — attach delegate agents (each with its own tools) to the agent(s).
    use_subagents = questionary.confirm(
        "Attach sub-agents (swarm) each agent can delegate tasks to?", default=False
    ).ask()

    # Deep agent mode — planning / filesystem / reflection toggles.
    deep_planning = deep_filesystem = deep_reflection = False
    if agent_mode == "deep":
        deep_planning = questionary.confirm(
            "  • Give it a write_todos planning tool (recommended)?", default=True
        ).ask()
        deep_filesystem = questionary.confirm(
            "  • Give it sandboxed filesystem tools (read/write/edit/list)?", default=True
        ).ask()
        deep_reflection = questionary.confirm(
            "  • Add a critic/reflection revision loop before the final answer?", default=False
        ).ask()

    # Voice I/O — speech-to-text + text-to-speech (local-first, keyless).
    use_voice = questionary.confirm(
        "Add voice I/O (speech-to-text + text-to-speech)?", default=False
    ).ask()

    # Streamlit UI — chat (+ voice) front-end.
    streamlit_ui = questionary.confirm(
        "Generate a Streamlit UI (chat" + (" + voice" if use_voice else "") + ")?", default=False
    ).ask()

    # Claw — multi-channel content assistant (intent router + webhook).
    claw = questionary.confirm(
        "Add the Claw multi-channel assistant (intent router + /claw webhook)?", default=False
    ).ask()

    custom_prompts = questionary.confirm("Scaffold custom prompt templates (vs defaults)?", default=False).ask()

    # Enterprise pack — bundle or pick individually
    enterprise = questionary.confirm(
        "Enable the enterprise pack (tracing, guardrails, FastAPI, Docker, CI, evals)?",
        default=False,
    ).ask()
    if enterprise:
        observability = guardrails = serve = docker = ci = evals = True
    else:
        observability = questionary.confirm("  • OpenTelemetry/Langfuse observability?", default=False).ask()
        guardrails = questionary.confirm("  • Input/output guardrails?", default=False).ask()
        serve = questionary.confirm("  • FastAPI server (REST + SSE)?", default=False).ask()
        docker = questionary.confirm("  • Dockerfile + docker-compose?", default=False).ask()
        ci = questionary.confirm("  • GitHub Actions CI?", default=False).ask()
        evals = questionary.confirm("  • LLM-as-judge eval harness?", default=False).ask()

    create_venv = questionary.confirm("Create a .venv with `uv` now?", default=True).ask()
    run_sync = False
    if create_venv:
        run_sync = questionary.confirm("Install dependencies now (`uv sync`)? (needs network)", default=False).ask()

    return ProjectSpec(
        name=name,
        framework=framework,
        provider=provider,
        model=model,
        agents=agents,
        orchestration=orchestration,
        agent_mode=agent_mode,
        use_rag=bool(use_rag),
        vector_store=vector_store,
        embedding_provider=embedding_provider,
        memory=memory or "none",
        use_mcp=bool(use_mcp),
        mcp_tools=list(mcp_tools),
        use_skills=bool(use_skills),
        use_subagents=bool(use_subagents),
        deep_planning=bool(deep_planning),
        deep_filesystem=bool(deep_filesystem),
        deep_reflection=bool(deep_reflection),
        use_voice=bool(use_voice),
        streamlit=bool(streamlit_ui),
        claw=bool(claw),
        prompt_style="custom" if custom_prompts else "default",
        observability=bool(observability),
        guardrails=bool(guardrails),
        serve=bool(serve),
        docker=bool(docker),
        ci=bool(ci),
        evals=bool(evals),
        create_venv=bool(create_venv),
        run_sync=bool(run_sync),
    )
