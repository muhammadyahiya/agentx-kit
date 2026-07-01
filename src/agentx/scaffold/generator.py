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
_COMMON_FILES: list[tuple[str, str]] = [
    ("pyproject.toml.j2", "pyproject.toml"),
    ("README.md.j2", "README.md"),
    ("env.example.j2", ".env.example"),
    ("gitignore.j2", ".gitignore"),
    ("pkg/__init__.py.j2", "src/{pkg}/__init__.py"),
    ("pkg/config.py.j2", "src/{pkg}/config.py"),
    ("pkg/prompts.py.j2", "src/{pkg}/prompts.py"),
    ("pkg/main.py.j2", "src/{pkg}/main.py"),
]

# A real LangGraph project: explicit state + nodes + graph + tool assembly.
_LANGGRAPH_FILES: list[tuple[str, str]] = [
    ("pkg/state.py.j2", "src/{pkg}/state.py"),
    ("pkg/tools.py.j2", "src/{pkg}/tools.py"),
    ("pkg/nodes.py.j2", "src/{pkg}/nodes.py"),
    ("pkg/graph.py.j2", "src/{pkg}/graph.py"),
]

# A real CrewAI project: agents + tasks + crew.
_CREWAI_FILES: list[tuple[str, str]] = [
    ("pkg/agents.py.j2", "src/{pkg}/agents.py"),
    ("pkg/tasks.py.j2", "src/{pkg}/tasks.py"),
    ("pkg/crew.py.j2", "src/{pkg}/crew.py"),
]


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
    # Deterministic order for reproducible pyproject output.
    order = ["langgraph", "crewai", "openai", "azure", "openrouter", "anthropic",
             "google", "vertex", "bedrock", "groq", "ollama", "rag", "mcp",
             "observability", "server"]
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
        plan.append(("pkg/rag.py.j2", "src/{pkg}/rag.py"))
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
            "memory": spec.memory,
            "mcp": spec.use_mcp,
            "skills": spec.use_skills,
            "observability": spec.observability,
            "guardrails": spec.guardrails,
            "serve": spec.serve,
            "docker": spec.docker,
            "ci": spec.ci,
            "evals": spec.evals,
            "cache": spec.use_cache,
        },
        "extras": _extras(spec),
        "telemetry_opt_out": False,
    }
    path = target / "agentx.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def generate_project(spec: ProjectSpec, target_dir: str | Path, overwrite: bool = False) -> GenerationResult:
    """Render the project for ``spec`` into ``target_dir``."""
    target = Path(target_dir).expanduser().resolve()
    if target.exists() and any(target.iterdir()) and not overwrite:
        raise FileExistsError(f"Target directory '{target}' exists and is not empty. Use overwrite=True.")
    target.mkdir(parents=True, exist_ok=True)

    env = _env()
    ctx = _context(spec)
    written: list[Path] = []
    messages: list[str] = []

    for template_name, out_rel in _COMMON_FILES + _conditional_files(spec):
        out_path = target / out_rel.format(pkg=spec.package)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        rendered = env.get_template(template_name).render(**ctx)
        out_path.write_text(rendered, encoding="utf-8")
        written.append(out_path)

    # Seed a knowledge/ directory when RAG or the MCP filesystem server needs one
    # (the restricted MCP server points at ./knowledge and RAG indexes it).
    if spec.use_rag or spec.use_mcp:
        knowledge_dir = target / "knowledge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        seed = knowledge_dir / "README.md"
        if not seed.exists():
            seed.write_text(
                f"# {spec.slug} knowledge base\n\n"
                "Drop `.txt` / `.md` files here. They are indexed for RAG"
                " and exposed (read-only) to the MCP filesystem tool.\n",
                encoding="utf-8",
            )
        written.append(seed)

    # The prompt source of truth — edited by hand or via `agentx prompt`.
    written.append(prompts_store.write_prompts(target, spec))
    # A single declarative manifest of the project (à la langgraph.json).
    written.append(_write_manifest(target, spec))

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
