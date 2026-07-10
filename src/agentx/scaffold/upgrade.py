"""Re-run the scaffolder's templates over an existing generated project —
powers ``agentx upgrade``.

Rebuilds a best-effort :class:`~agentx.scaffold.spec.ProjectSpec` from
``agentx.json`` (plus ``prompts.json`` for each agent's role/goal/system
prompt, which the manifest doesn't carry), regenerates every templated file
into a fresh temp directory with the *current* installed agentx-kit's
templates, and diffs it against the live project — nothing is written to the
real project until the caller explicitly applies the plan.

Known limitation: if the manifest's ``domain`` was auto-inferred (not set
explicitly) and ended up generic ("none"), re-running inference here uses
only the project name (the original ``problem_statement`` free-text used at
scaffold time isn't persisted anywhere) — in the rare case that mattered, the
inferred domain could differ slightly from the original.
"""
from __future__ import annotations

import filecmp
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .generator import generate_project
from .spec import AgentSpec, ProjectSpec

#: Files never touched by --apply unless --force is also given — meant to be
#: hand/CLI-edited (prompts.json via `agentx prompt`) or user-populated
#: (knowledge/), not silently regenerated.
_PROTECTED_RELATIVE_PATHS = {"prompts.json"}
_PROTECTED_PREFIXES = ("knowledge/", "data/skills/")


@dataclass
class DiffEntry:
    relative_path: str
    status: str   # "new" | "changed" | "protected"


def _spec_from_manifest(root: Path, manifest: dict) -> ProjectSpec:
    features = manifest.get("features", {}) or {}
    prompt_agents: dict = {}
    prompts_path = root / "prompts.json"
    if prompts_path.exists():
        try:
            prompt_agents = json.loads(prompts_path.read_text(encoding="utf-8")).get("agents", {})
        except json.JSONDecodeError:
            prompt_agents = {}

    agent_names = manifest.get("agents") or ["assistant"]
    agents = [
        AgentSpec(
            name=name,
            role=(prompt_agents.get(name, {}) or {}).get("role") or "Helpful Assistant",
            goal=(prompt_agents.get(name, {}) or {}).get("goal")
                 or "Help the user accomplish their task accurately.",
            system_prompt=(prompt_agents.get(name, {}) or {}).get("system_prompt") or "",
        )
        for name in agent_names
    ]

    return ProjectSpec(
        name=manifest.get("name", "app"),
        framework=manifest.get("framework", "langgraph"),
        provider=manifest.get("provider", "openai"),
        model=manifest.get("model", ""),
        agents=agents,
        orchestration=manifest.get("orchestration", "supervisor"),
        use_rag=bool(features.get("rag")),
        vector_store=features.get("vector_store") or "chroma",
        embedding_provider=features.get("embedding_provider") or "",
        agent_mode=features.get("agent_mode") or "chat",
        deep_planning=bool(features.get("deep_planning", True)),
        deep_filesystem=bool(features.get("deep_filesystem", True)),
        deep_reflection=bool(features.get("deep_reflection", False)),
        domain=manifest.get("domain") or "",
        seed_domain_kb=False,  # never re-seed data/skills/ on upgrade — see _PROTECTED_PREFIXES
        memory=features.get("memory") or "none",
        use_mcp=bool(features.get("mcp")),
        mcp_tools=list(features.get("mcp_tools") or []),
        use_skills=bool(features.get("skills")),
        use_voice=bool(features.get("voice")),
        use_subagents=bool(features.get("subagents")),
        streamlit=bool(features.get("streamlit")),
        claw=bool(features.get("claw")),
        observability=bool(features.get("observability")),
        guardrails=bool(features.get("guardrails")),
        serve=bool(features.get("serve")),
        docker=bool(features.get("docker")),
        ci=bool(features.get("ci")),
        evals=bool(features.get("evals")),
        use_cache=bool(features.get("cache")),
        create_venv=False,
        run_sync=False,
    )


def _is_protected(rel: str) -> bool:
    if rel in _PROTECTED_RELATIVE_PATHS:
        return True
    return any(rel.startswith(prefix) for prefix in _PROTECTED_PREFIXES)


def plan_upgrade(root: Path, manifest: dict) -> tuple[Path, list[DiffEntry]]:
    """Regenerate the project's templated files into a fresh temp directory
    and diff them against ``root``.

    Returns ``(staging_dir, diff_entries)`` — the caller applies the plan
    with :func:`apply_upgrade` and is responsible for cleaning up
    ``staging_dir`` afterward (e.g. ``shutil.rmtree(staging_dir.parent)``).
    """
    spec = _spec_from_manifest(root, manifest)
    staging_parent = Path(tempfile.mkdtemp(prefix="agentx-upgrade-"))
    result = generate_project(spec, staging_parent / "generated", overwrite=True)
    # generate_project resolves its target (symlinks, ..); take the resolved
    # path back from the result rather than our own pre-resolve copy, or
    # `.relative_to()` below can fail on a platform where the temp dir itself
    # is behind a symlink (e.g. macOS's /tmp -> /private/tmp).
    staging_target = result.target_dir

    entries: list[DiffEntry] = []
    for new_file in result.files:
        rel = str(new_file.relative_to(staging_target))
        live_file = root / rel
        if _is_protected(rel):
            if live_file.exists() and not filecmp.cmp(new_file, live_file, shallow=False):
                entries.append(DiffEntry(rel, "protected"))
            continue
        if not live_file.exists():
            entries.append(DiffEntry(rel, "new"))
        elif not filecmp.cmp(new_file, live_file, shallow=False):
            entries.append(DiffEntry(rel, "changed"))
    return staging_target, entries


def apply_upgrade(root: Path, staging_target: Path, entries: list[DiffEntry], *, force: bool = False) -> list[str]:
    """Copy ``new``/``changed`` (and, with ``force``, ``protected``) entries
    from ``staging_target`` into ``root``. Returns the relative paths
    actually written."""
    written: list[str] = []
    for entry in entries:
        if entry.status == "protected" and not force:
            continue
        src = staging_target / entry.relative_path
        dst = root / entry.relative_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        written.append(entry.relative_path)
    return written


__all__ = ["DiffEntry", "plan_upgrade", "apply_upgrade"]
