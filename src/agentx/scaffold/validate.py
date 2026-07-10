"""Structural validation for a generated project's ``agentx.json`` manifest.

Powers ``agentx validate``. Pure/testable, same as :mod:`agentx.scaffold.graphviz`
— everything is derived from the manifest (plus a light look at sibling files
like ``pyproject.toml``/``prompts.json``), nothing is imported or executed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..providers import get_spec

_VALID_FRAMEWORKS = {"langgraph", "crewai"}
_VALID_AGENT_MODES = {"chat", "autonomous", "research", "deep"}
_VALID_ORCHESTRATIONS = {"supervisor", "sequential", "parallel"}
_VALID_MEMORY = {"none", "short", "long", "both"}
_REQUIRED_TOP_LEVEL_KEYS = ("name", "framework", "provider", "agents", "features", "extras")


@dataclass
class Finding:
    level: str    # "error" | "warning"
    message: str


def _check_mcp_tools(features: dict) -> list[Finding]:
    if not features.get("mcp"):
        return []
    from ..tools.mcp_server import AVAILABLE_MCP_TOOLS

    tools = features.get("mcp_tools") or []
    unknown = sorted(set(tools) - set(AVAILABLE_MCP_TOOLS))
    if unknown:
        return [Finding("error", f"features.mcp_tools has unknown tool(s): {unknown}")]
    return []


def validate_manifest(root: Path, manifest: dict) -> list[Finding]:
    """Structural checks on an already-loaded manifest dict, plus a light
    look at sibling files in ``root`` (the project's root directory)."""
    findings: list[Finding] = []

    for key in _REQUIRED_TOP_LEVEL_KEYS:
        if key not in manifest:
            findings.append(Finding("error", f"Missing required key: {key!r}"))

    framework = manifest.get("framework")
    if framework is not None and framework not in _VALID_FRAMEWORKS:
        findings.append(Finding("error", f"Unknown framework {framework!r} (expected one of {sorted(_VALID_FRAMEWORKS)})"))

    provider = manifest.get("provider")
    if provider is not None:
        try:
            get_spec(provider)
        except KeyError:
            findings.append(Finding("error", f"Unknown provider {provider!r} (run `agentx providers` for valid ids)"))

    agents = manifest.get("agents")
    if isinstance(agents, list) and not agents:
        findings.append(Finding("warning", "agents list is empty — the project won't run any agent"))

    orchestration = manifest.get("orchestration")
    if orchestration is not None and orchestration not in _VALID_ORCHESTRATIONS:
        findings.append(Finding("warning", f"Unknown orchestration {orchestration!r} (expected one of {sorted(_VALID_ORCHESTRATIONS)})"))

    features = manifest.get("features") or {}
    if not isinstance(features, dict):
        findings.append(Finding("error", "features must be an object"))
    else:
        agent_mode = features.get("agent_mode")
        if agent_mode is not None and agent_mode not in _VALID_AGENT_MODES:
            findings.append(Finding("warning", f"Unknown features.agent_mode {agent_mode!r} (expected one of {sorted(_VALID_AGENT_MODES)})"))
        memory = features.get("memory")
        if memory is not None and memory not in _VALID_MEMORY:
            findings.append(Finding("warning", f"Unknown features.memory {memory!r} (expected one of {sorted(_VALID_MEMORY)})"))
        findings.extend(_check_mcp_tools(features))

    extras = manifest.get("extras")
    if extras is not None and not isinstance(extras, list):
        findings.append(Finding("error", "extras must be a list of strings"))

    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        findings.append(Finding("warning", "pyproject.toml not found next to agentx.json"))
    elif isinstance(extras, list) and extras:
        text = pyproject.read_text(encoding="utf-8")
        missing_extras = [e for e in extras if e not in text]
        if missing_extras:
            findings.append(Finding(
                "warning",
                f"pyproject.toml doesn't mention extra(s) {missing_extras} declared in agentx.json — "
                "dependencies may be out of sync (was pyproject.toml hand-edited?)",
            ))

    prompts_path = root / "prompts.json"
    if prompts_path.exists():
        try:
            prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            findings.append(Finding("error", f"prompts.json is not valid JSON: {exc}"))
        else:
            prompt_agents = set(prompts.get("agents", {}))
            manifest_agents = set(agents) if isinstance(agents, list) else set()
            missing = manifest_agents - prompt_agents
            if missing:
                findings.append(Finding(
                    "warning",
                    f"agent(s) {sorted(missing)} listed in agentx.json have no entry in prompts.json",
                ))

    env_example = root / ".env.example"
    if not env_example.exists():
        findings.append(Finding("warning", ".env.example not found — credential setup instructions may be missing"))

    return findings


__all__ = ["Finding", "validate_manifest"]
