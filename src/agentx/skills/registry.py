"""Filesystem-backed skill registry.

A *skill* is a named instruction block (e.g. "Always use the STAR method") that
gets injected into agent prompts, optionally bundled with the tool/MCP-server
names the skill needs. Skills are stored as JSON files under a directory so
users can add/version them outside the code.

The ``Skill`` dataclass is backward-compatible: skill JSON written by older
versions (only ``slug``/``name``/``description``/``instructions``) still loads,
and the new ``tools``/``mcp_servers``/``tags``/``version`` fields default empty.
"""
from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "skill"


@dataclass
class Skill:
    slug: str
    name: str
    description: str
    instructions: str
    # v2 fields — optional, backward-compatible.
    tools: list[str] = field(default_factory=list)        # built-in tool names the skill uses
    mcp_servers: list[str] = field(default_factory=list)  # mcp_servers.json keys
    tags: list[str] = field(default_factory=list)         # e.g. ["legal", "writing"]
    version: str = "1"

    @classmethod
    def from_dict(cls, d: dict) -> "Skill":
        """Build a Skill from a dict, ignoring unknown keys (forward-compat)."""
        known = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


class SkillRegistry:
    def __init__(self, directory: str | Path):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    def add(
        self,
        name: str,
        description: str,
        instructions: str,
        *,
        tools: list[str] | None = None,
        mcp_servers: list[str] | None = None,
        tags: list[str] | None = None,
        version: str = "1",
    ) -> Skill:
        if not name.strip():
            raise ValueError("Skill name is required.")
        skill = Skill(
            _slug(name), name.strip(), description.strip(), instructions.strip(),
            tools=list(tools or []), mcp_servers=list(mcp_servers or []),
            tags=list(tags or []), version=version,
        )
        (self.dir / f"{skill.slug}.json").write_text(
            json.dumps(asdict(skill), indent=2), encoding="utf-8"
        )
        return skill

    def list(self) -> list[Skill]:
        out: list[Skill] = []
        for fp in sorted(self.dir.glob("*.json")):
            try:
                out.append(Skill.from_dict(json.loads(fp.read_text(encoding="utf-8"))))
            except Exception:  # noqa: BLE001 - skip malformed files
                continue
        return out

    def get(self, slug: str) -> Skill | None:
        for s in self.list():
            if s.slug == slug:
                return s
        return None

    def delete(self, slug: str) -> None:
        (self.dir / f"{slug}.json").unlink(missing_ok=True)

    def combined_instructions(self, slugs: list[str] | None = None) -> str:
        """Concatenate selected (or all) skills' instructions for prompt injection."""
        skills = self.list()
        if slugs:
            wanted = set(slugs)
            skills = [s for s in skills if s.slug in wanted]
        if not skills:
            return ""
        return "\n".join(f"- {s.name}: {s.instructions}" for s in skills)

    def tool_names(self, slugs: list[str] | None = None) -> list[str]:
        """Distinct built-in tool names required by the selected (or all) skills."""
        skills = self.list()
        if slugs:
            wanted = set(slugs)
            skills = [s for s in skills if s.slug in wanted]
        seen: list[str] = []
        for s in skills:
            for t in s.tools:
                if t not in seen:
                    seen.append(t)
        return seen


def get_skill_registry(directory: str | Path = "data/skills") -> SkillRegistry:
    return SkillRegistry(directory)
