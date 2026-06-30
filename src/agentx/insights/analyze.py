"""Heuristic prompt analysis — quality score, suggestions, and limit warnings.

Offline and fast (no LLM). Encodes widely-recommended prompt-engineering levers
(2025–2026): a clear role + goal, explicit output format, examples, constraints,
lean/keyword-led wording, and context-window awareness. Use this for instant
feedback while editing; use :mod:`agentx.insights.optimize` for an LLM rewrite.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .tokens import context_window, count_tokens, utilization

_VAGUE = ("something", "stuff", "etc", "and so on", "good", "nice", "appropriate", "as needed")
_FORMAT_HINTS = ("json", "markdown", "bullet", "list", "table", "format", "schema", "output:", "respond with")
_EXAMPLE_HINTS = ("example", "e.g.", "for instance", "input:", "output:")
_CONSTRAINT_HINTS = ("must", "do not", "don't", "never", "only", "limit", "at most", "no more than", "avoid")
_ROLE_HINTS = ("you are", "act as", "your role", "as a ")
_GOAL_HINTS = ("your goal", "your task", "objective", "you should", "help the user", "your job")


@dataclass
class PromptAnalysis:
    tokens: int
    chars: int
    quality_score: int                     # 0-100
    checks: dict[str, bool] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def analyze_prompt(text: str, model: str = "gpt-4o-mini") -> PromptAnalysis:
    """Score a prompt and return actionable suggestions + limit warnings."""
    text = text or ""
    low = text.lower()
    tokens = count_tokens(text, model)

    checks = {
        "has_role": any(h in low for h in _ROLE_HINTS),
        "has_goal": any(h in low for h in _GOAL_HINTS),
        "has_output_format": any(h in low for h in _FORMAT_HINTS),
        "has_examples": any(h in low for h in _EXAMPLE_HINTS),
        "has_constraints": any(h in low for h in _CONSTRAINT_HINTS),
        "not_vague": not any(re.search(rf"\b{re.escape(w)}\b", low) for w in _VAGUE),
        "reasonable_length": 5 <= tokens <= 1500,
    }
    # Weighted score (role + goal + format matter most).
    weights = {
        "has_role": 18, "has_goal": 18, "has_output_format": 18,
        "has_examples": 14, "has_constraints": 14, "not_vague": 10, "reasonable_length": 8,
    }
    score = sum(w for k, w in weights.items() if checks[k])

    suggestions: list[str] = []
    if not checks["has_role"]:
        suggestions.append("Open with an explicit role, e.g. “You are a senior support agent…”.")
    if not checks["has_goal"]:
        suggestions.append("State the goal/task clearly so the model knows what success looks like.")
    if not checks["has_output_format"]:
        suggestions.append("Specify the output format (JSON/markdown/bullets) — reduces retries and tokens.")
    if not checks["has_examples"]:
        suggestions.append("Add 1–2 short input→output examples (few-shot) for tricky tasks.")
    if not checks["has_constraints"]:
        suggestions.append("Add constraints/guardrails (length caps, “do not …”) to keep output on-task.")
    if not checks["not_vague"]:
        suggestions.append("Replace vague words (e.g. “good”, “appropriate”, “stuff”) with concrete criteria.")

    warnings: list[str] = []
    win = context_window(model)
    util = utilization(tokens, model)
    if tokens > 1500:
        warnings.append(
            f"Prompt is long ({tokens} tokens). Lead with keywords, trim boilerplate, and move "
            "stable context into a cached prefix to cut cost."
        )
    if util >= 0.5:
        warnings.append(f"Prompt already uses {util:.0%} of {model}'s {win:,}-token context window.")
    if tokens < 5:
        warnings.append("Prompt is very short — likely under-specified.")

    return PromptAnalysis(
        tokens=tokens, chars=len(text), quality_score=score,
        checks=checks, suggestions=suggestions, warnings=warnings,
    )
