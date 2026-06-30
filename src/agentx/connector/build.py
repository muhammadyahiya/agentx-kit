"""Turn a problem statement (+ optional overrides) into a generated project.

Pure orchestration over the scaffolder — no MCP dependency — so it's testable
and reusable. The MCP tools in ``server.py`` are thin wrappers around this.
"""
from __future__ import annotations

from pathlib import Path

from ..scaffold import AgentSpec, ProjectSpec, generate_project
from .recommend import recommend_spec

_ALL_FEATURES = ["rag", "memory", "mcp", "skills", "observability", "guardrails", "serve", "docker", "ci", "evals"]
_KEY_FILES_MAX = 6000


def _apply_features(spec: ProjectSpec, features: list[str]) -> None:
    fl = set(features or [])
    spec.use_rag = "rag" in fl
    spec.memory = "both" if "memory" in fl else "none"
    spec.use_mcp = "mcp" in fl
    spec.use_skills = "skills" in fl
    spec.observability = "observability" in fl
    spec.guardrails = "guardrails" in fl
    spec.serve = "serve" in fl
    spec.docker = "docker" in fl
    spec.ci = "ci" in fl
    spec.evals = "evals" in fl


def build_project_from_statement(
    problem_statement: str,
    name: str = "",
    framework: str = "",
    provider: str = "",
    model: str = "",
    agents: int = 0,
    features: list[str] | None = None,
    enterprise: bool = False,
    output_dir: str = "",
    create_venv: bool = False,
    overwrite: bool = True,
) -> dict:
    """Generate a complete project for a problem statement; return a summary."""
    rec = recommend_spec(problem_statement)
    name = name or rec["name"]
    framework = framework or rec["framework"]
    provider = provider or rec["provider"]
    model = model or rec["model"]
    n_agents = agents or rec["agents"]
    feats = list(features) if features is not None else list(rec["features"])

    # First agent carries the role/goal/prompt derived from the problem statement.
    agent_specs = [AgentSpec(name="assistant" if n_agents == 1 else "agent_1",
                             role=rec["role"], goal=rec["goal"], system_prompt=rec["system_prompt"])]
    for i in range(1, n_agents):
        agent_specs.append(AgentSpec(name=f"agent_{i + 1}", role=rec["role"]))

    spec = ProjectSpec(
        name=name, framework=framework, provider=provider, model=model,
        agents=agent_specs, prompt_style="custom", create_venv=create_venv,
    )
    if enterprise:
        spec.enable_enterprise()
        feats = _ALL_FEATURES
    else:
        _apply_features(spec, feats)

    target = Path(output_dir).expanduser() if output_dir else Path.cwd() / spec.slug
    result = generate_project(spec, target, overwrite=overwrite)
    root = result.target_dir

    # Collect a compact view for the calling LLM.
    tree = sorted(str(p.relative_to(root)) for p in root.glob("**/*") if p.is_file())
    pkg = spec.package
    key_paths = [
        "pyproject.toml", "prompts.json", "agentx.json",
        f"src/{pkg}/main.py", f"src/{pkg}/agents.py", f"src/{pkg}/prompts.py",
    ]
    if spec.serve:
        key_paths.append(f"src/{pkg}/server.py")
    key_files = {}
    for rel in key_paths:
        fp = root / rel
        if fp.exists():
            key_files[rel] = fp.read_text(encoding="utf-8")[:_KEY_FILES_MAX]

    run_cmd = (
        f"uv run uvicorn {pkg}.server:app --reload" if spec.serve else f"uv run {spec.slug}"
    )
    next_steps = [
        f"cd {root.name}",
        "cp .env.example .env   # add your provider API key(s)",
        "uv venv && uv sync",
        run_cmd,
    ]

    return {
        "ok": True,
        "target_dir": str(root),
        "name": spec.slug,
        "framework": framework,
        "provider": provider,
        "model": model or "(provider default)",
        "agents": [a.name for a in agent_specs],
        "features": feats,
        "rationale": rec["rationale"],
        "file_tree": tree,
        "key_files": key_files,
        "next_steps": next_steps,
    }
