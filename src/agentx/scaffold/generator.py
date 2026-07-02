"""Project generator — renders templates into a new project and sets up uv.

``generate_project(spec, target_dir)`` is pure/testable: it writes files and,
unless disabled, runs ``uv venv`` (creating ``.venv``) and optionally ``uv sync``.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ..providers import get_spec
from . import prompts_store
from .spec import ProjectSpec

TEMPLATES_DIR = Path(__file__).parent / "templates"

# (template, output-relative-path) — output paths use {pkg} placeholder.
# Generated projects use a structured, folder-per-concern layout:
#   config.py · main.py            — entrypoints / settings
#   state/    schemas/  prompts/   — graph state · I/O models · prompt registry
#   nodes/    graph.py             — one module per agent + the assembled graph
#   utils/    (llm/tools/rag/…)    — provider wiring, tool assembly, retrieval
#   libs/     (agent_factory/…)    — shared building blocks (worker/coercion/voice)
_COMMON_FILES: list[tuple[str, str]] = [
    ("pyproject.toml.j2", "pyproject.toml"),
    ("README.md.j2", "README.md"),
    ("env.example.j2", ".env.example"),
    ("gitignore.j2", ".gitignore"),
    ("pkg/__init__.py.j2", "src/{pkg}/__init__.py"),
    ("pkg/config.py.j2", "src/{pkg}/config.py"),
    ("pkg/libs/__init__.py.j2", "src/{pkg}/libs/__init__.py"),
    ("pkg/libs/logging_setup.py.j2", "src/{pkg}/libs/logging_setup.py"),
    ("pkg/prompts/__init__.py.j2", "src/{pkg}/prompts/__init__.py"),
    ("pkg/schemas/__init__.py.j2", "src/{pkg}/schemas/__init__.py"),
    ("pkg/utils/__init__.py.j2", "src/{pkg}/utils/__init__.py"),
    ("pkg/utils/llm.py.j2", "src/{pkg}/utils/llm.py"),
    ("pkg/main.py.j2", "src/{pkg}/main.py"),
]

# A real LangGraph project: explicit state + per-agent nodes + graph + tools.
_LANGGRAPH_FILES: list[tuple[str, str]] = [
    ("pkg/state/__init__.py.j2", "src/{pkg}/state/__init__.py"),
    ("pkg/utils/tools.py.j2", "src/{pkg}/utils/tools.py"),
    ("pkg/libs/agent_factory.py.j2", "src/{pkg}/libs/agent_factory.py"),
    ("pkg/nodes/__init__.py.j2", "src/{pkg}/nodes/__init__.py"),
    ("pkg/graph.py.j2", "src/{pkg}/graph.py"),
]

# A real CrewAI project: agents + tasks + crew (also uses utils/ + prompts/).
_CREWAI_FILES: list[tuple[str, str]] = [
    ("pkg/utils/tools.py.j2", "src/{pkg}/utils/tools.py"),
    ("pkg/agents.py.j2", "src/{pkg}/agents.py"),
    ("pkg/tasks.py.j2", "src/{pkg}/tasks.py"),
    ("pkg/crew.py.j2", "src/{pkg}/crew.py"),
]


def _apply_domain(spec: ProjectSpec):
    """Infer (or look up) a domain and tailor the first agent + features in place.

    Returns the resolved ``Domain`` (or ``None``). Sets the first agent's role +
    system prompt to the domain expert persona when the agent has no explicit
    prompt, enables RAG so the seeded knowledge base is indexed, and records the
    domain for the manifest + KB seeding.
    """
    from .domains import get_domain, infer_domain

    if spec.domain == "none":
        return None
    dom = get_domain(spec.domain) if spec.domain else infer_domain(spec.name, spec.problem_statement)
    if dom is None:
        return None

    first = spec.agents[0] if spec.agents else None
    if first is not None and not (first.system_prompt or "").strip():
        first.system_prompt = dom.system_prompt
        if first.role in ("", "Helpful Assistant", "Assistant"):
            first.role = dom.label
    # A domain agent is only useful with a knowledge base — turn RAG on.
    if spec.seed_domain_kb:
        spec.use_rag = True
    spec.domain = dom.key   # persist the resolved domain for the manifest
    return dom


@dataclass
class GenerationResult:
    target_dir: Path
    files: list[Path]
    venv_created: bool
    synced: bool
    messages: list[str]


def _extras(spec: ProjectSpec) -> list[str]:
    """Compute the agentx extras the generated project needs."""
    extras = {get_spec(spec.provider).extra}
    extras.add("langgraph" if spec.framework == "langgraph" else "crewai")
    if spec.use_rag:
        extras.add("rag")
    if spec.use_mcp:
        extras.add("mcp")
    if spec.observability:
        extras.add("observability")
    if spec.serve:
        extras.add("server")
    if spec.use_voice:
        extras.add("voice")
    if spec.streamlit or spec.claw:
        extras.add("streamlit")
    # Deterministic order for reproducible pyproject output.
    if spec.use_rag:
        # Add embedding provider extra when explicitly set
        if spec.embedding_provider in {"huggingface", "hf"}:
            extras.add("huggingface")
        elif spec.embedding_provider == "cohere":
            extras.add("cohere")
        elif spec.embedding_provider == "voyage":
            extras.add("voyage")
        # Add FAISS extra when selected
        if spec.vector_store == "faiss":
            extras.add("faiss")

    order = ["langgraph", "crewai", "openai", "azure", "openrouter", "anthropic",
             "google", "vertex", "bedrock", "groq", "ollama", "huggingface",
             "cohere", "voyage", "rag", "faiss", "mcp", "observability", "server",
             "voice", "streamlit"]
    return [e for e in order if e in extras]


def _context(spec: ProjectSpec) -> dict:
    provider_spec = get_spec(spec.provider)
    return {
        "spec": spec,
        "pkg": spec.package,
        "model": spec.model or provider_spec.default_model,
        "provider_label": provider_spec.label,
        "provider_env": list(provider_spec.env_vars),
        "extras": _extras(spec),
        "extras_str": ",".join(_extras(spec)),
        "multi_agent": len(spec.agents) > 1,
        "orchestration": spec.orchestration,
        "use_voice": spec.use_voice,
        "use_subagents": spec.use_subagents,
        "streamlit": spec.streamlit,
        "claw": spec.claw,
    }


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )


def _conditional_files(spec: ProjectSpec) -> list[tuple[str, str]]:
    plan: list[tuple[str, str]] = []
    # Framework-specific core (real project structure).
    plan += _LANGGRAPH_FILES if spec.framework == "langgraph" else _CREWAI_FILES
    if spec.use_rag:
        plan.append(("pkg/utils/embeddings.py.j2", "src/{pkg}/utils/embeddings.py"))
        plan.append(("pkg/utils/rag.py.j2", "src/{pkg}/utils/rag.py"))
        plan.append(("pkg/utils/retriever.py.j2", "src/{pkg}/utils/retriever.py"))
    if spec.use_voice:
        plan.append(("pkg/libs/voice.py.j2", "src/{pkg}/libs/voice.py"))
    if spec.needs_memory:
        plan.append(("pkg/memory.py.j2", "src/{pkg}/memory.py"))
    if spec.use_mcp:
        plan.append(("mcp_servers.json.j2", "mcp_servers.json"))
    if spec.use_skills:
        plan.append(("skills_seed.json.j2", "data/skills/star-method.json"))
    if spec.observability:
        plan.append(("pkg/observability.py.j2", "src/{pkg}/observability.py"))
    if spec.guardrails:
        plan.append(("pkg/guardrails.py.j2", "src/{pkg}/guardrails.py"))
    if spec.serve:
        plan.append(("pkg/server.py.j2", "src/{pkg}/server.py"))
    if spec.claw:
        plan.append(("pkg/claw/__init__.py.j2", "src/{pkg}/claw/__init__.py"))
        plan.append(("pkg/claw/intent.py.j2", "src/{pkg}/claw/intent.py"))
        plan.append(("pkg/claw/assistant.py.j2", "src/{pkg}/claw/assistant.py"))
        plan.append(("pkg/claw/webhook.py.j2", "src/{pkg}/claw/webhook.py"))
    if spec.streamlit:
        plan.append(("streamlit_app.py.j2", "streamlit_app.py"))
    if spec.docker:
        plan.append(("Dockerfile.j2", "Dockerfile"))
        plan.append(("docker-compose.yml.j2", "docker-compose.yml"))
        plan.append(("dockerignore.j2", ".dockerignore"))
    if spec.ci:
        plan.append(("ci.yml.j2", ".github/workflows/ci.yml"))
    if spec.evals:
        plan.append(("evals/run_evals.py.j2", "evals/run_evals.py"))
        plan.append(("evals/dataset.json.j2", "evals/dataset.json"))
    return plan


def _render_nodes(env, ctx: dict, spec: ProjectSpec, staging: Path) -> list[Path]:
    """Render per-agent node modules for a LangGraph project.

    Single-agent  → nodes/agent.py
    Multi-agent   → nodes/<agent_name>.py for each agent (+ nodes/supervisor.py
                    when orchestration == 'supervisor').
    """
    written: list[Path] = []
    pkg_nodes = staging / "src" / spec.package / "nodes"
    pkg_nodes.mkdir(parents=True, exist_ok=True)

    if len(spec.agents) <= 1:
        agent = spec.agents[0] if spec.agents else None
        out = pkg_nodes / "agent.py"
        out.write_text(
            env.get_template("pkg/nodes/agent.py.j2").render(agent=agent, **ctx),
            encoding="utf-8",
        )
        written.append(out)
        return written

    # Multi-agent: one module per agent (deduped, snake-cased names).
    seen: set[str] = set()
    for i, agent in enumerate(spec.agents):
        if agent.name in seen:
            continue
        seen.add(agent.name)
        out = pkg_nodes / f"{agent.name}.py"
        out.write_text(
            env.get_template("pkg/nodes/worker.py.j2").render(
                agent=agent, agent_index=i, **ctx
            ),
            encoding="utf-8",
        )
        written.append(out)

    if spec.orchestration == "supervisor":
        out = pkg_nodes / "supervisor.py"
        out.write_text(
            env.get_template("pkg/nodes/supervisor.py.j2").render(**ctx),
            encoding="utf-8",
        )
        written.append(out)
    return written


def _write_manifest(target: Path, spec: ProjectSpec) -> Path:
    """Write agentx.json — a declarative summary of the generated project."""
    import json

    manifest = {
        "name": spec.slug,
        "framework": spec.framework,
        "provider": spec.provider,
        "model": spec.model or get_spec(spec.provider).default_model,
        "python_version": ">=3.10,<3.14",
        "agents": [a.name for a in spec.agents],
        "orchestration": spec.orchestration,
        "features": {
            "rag": spec.use_rag,
            "vector_store": spec.vector_store if spec.use_rag else None,
            "embedding_provider": spec.embedding_provider if spec.use_rag else None,
            "agent_mode": spec.agent_mode,
            "memory": spec.memory,
            "mcp": spec.use_mcp,
            "skills": spec.use_skills,
            "voice": spec.use_voice,
            "subagents": spec.use_subagents,
            "streamlit": spec.streamlit,
            "claw": spec.claw,
            "observability": spec.observability,
            "guardrails": spec.guardrails,
            "serve": spec.serve,
            "docker": spec.docker,
            "ci": spec.ci,
            "evals": spec.evals,
            "cache": spec.use_cache,
        },
        "domain": (spec.domain if spec.domain and spec.domain != "none" else None),
        "extras": _extras(spec),
        "telemetry_opt_out": False,
    }
    path = target / "agentx.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def generate_project(spec: ProjectSpec, target_dir: str | Path, overwrite: bool = False) -> GenerationResult:
    """Render the project for ``spec`` into ``target_dir`` atomically.

    Files are first rendered into a sibling temp directory and only moved into
    place once every template has been rendered successfully.  This prevents
    partial project trees when generation is interrupted.
    """
    import tempfile as _tempfile

    target = Path(target_dir).expanduser().resolve()
    if target.exists() and any(target.iterdir()) and not overwrite:
        raise FileExistsError(f"Target directory '{target}' exists and is not empty. Use overwrite=True.")
    target.parent.mkdir(parents=True, exist_ok=True)

    # Tailor the first agent + features to an inferred/explicit domain (mutates spec).
    domain = _apply_domain(spec)

    env = _env()
    ctx = _context(spec)
    messages: list[str] = []

    # Render into a temp dir alongside the target so shutil.move is a rename
    # on the same filesystem (fast + atomic within-fs).
    staging = Path(_tempfile.mkdtemp(prefix=f"{spec.slug}.", dir=str(target.parent)))
    try:
        staged_written: list[Path] = []

        for template_name, out_rel in _COMMON_FILES + _conditional_files(spec):
            out_path = staging / out_rel.format(pkg=spec.package)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            rendered = env.get_template(template_name).render(**ctx)
            out_path.write_text(rendered, encoding="utf-8")
            staged_written.append(out_path)

        # LangGraph: render one node module per agent (nodes/<name>.py), plus a
        # supervisor router when in supervisor mode. This gives users the
        # per-agent file layout (node1.py, node2.py …) they can edit directly.
        if spec.framework == "langgraph":
            staged_written += _render_nodes(env, ctx, spec, staging)

        # Seed knowledge/ when needed.
        if spec.use_rag or spec.use_mcp:
            knowledge_dir = staging / "knowledge"
            knowledge_dir.mkdir(parents=True, exist_ok=True)
            seed = knowledge_dir / "README.md"
            seed.write_text(
                f"# {spec.slug} knowledge base\n\n"
                "Drop PDF, Excel, CSV, Word, TXT, or Markdown files here. "
                "They are indexed for RAG and exposed (read-only) to the MCP "
                "filesystem tool.\n",
                encoding="utf-8",
            )
            staged_written.append(seed)

            # Seed a domain-specific primer so RAG has real content on first run.
            if domain is not None and spec.seed_domain_kb:
                primer = knowledge_dir / f"{domain.key}-primer.md"
                primer.write_text(domain.knowledge_seed, encoding="utf-8")
                staged_written.append(primer)

        staged_written.append(prompts_store.write_prompts(staging, spec))
        staged_written.append(_write_manifest(staging, spec))

        # Atomic swap: move staging → target. If target exists (overwrite=True),
        # remove it first.
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(staging), str(target))
    except Exception:
        # Clean up the incomplete staging directory on any failure.
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        raise

    # Re-glob the target for the final list of written files (used for reporting).
    written: list[Path] = [p for p in target.rglob("*") if p.is_file()]

    venv_created = synced = False
    uv = shutil.which("uv")
    if spec.create_venv:
        if not uv:
            messages.append("`uv` not found on PATH — skipped .venv creation. Install uv: https://docs.astral.sh/uv/")
        else:
            try:
                subprocess.run([uv, "venv"], cwd=target, check=True, capture_output=True, timeout=120)
                venv_created = True
                messages.append("Created .venv via `uv venv`.")
            except Exception as exc:  # noqa: BLE001
                messages.append(f"`uv venv` failed: {exc!r}")
            if venv_created and spec.run_sync:
                try:
                    subprocess.run([uv, "sync"], cwd=target, check=True, timeout=900)
                    synced = True
                    messages.append("Installed dependencies via `uv sync`.")
                except Exception as exc:  # noqa: BLE001
                    messages.append(f"`uv sync` failed (run it manually): {exc!r}")

    return GenerationResult(target, written, venv_created, synced, messages)
