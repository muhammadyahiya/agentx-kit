"""LLM-backed prompt refinement — rewrite a prompt while preserving intent.

Implements the "iterative refinement" pattern: improve an existing prompt by
applying best practices (clear role/goal, explicit output format, constraints,
lean wording) and any user feedback, *without* changing the original intent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..providers import get_chat_model

logger = logging.getLogger(__name__)

_OPTIMIZER_SYSTEM = (
    "You are a senior prompt engineer. You rewrite system prompts to be clearer, "
    "more reliable, and more token-efficient WITHOUT changing their intent.\n"
    "Apply: an explicit role + goal, a specified output format, concrete constraints, "
    "lean keyword-led wording, and few-shot examples only if they add value. "
    "Remove redundancy and vagueness. Keep it as short as possible while complete."
)

_OPTIMIZER_HUMAN = (
    "Rewrite the PROMPT below.\n\n"
    "PROMPT:\n{prompt}\n\n"
    "{feedback_block}"
    "Respond in EXACTLY this format:\n"
    "===IMPROVED===\n<the improved prompt only>\n===RATIONALE===\n"
    "<3-5 bullet points explaining the key changes>"
)


@dataclass
class OptimizationResult:
    original: str
    improved: str
    rationale: str
    ok: bool = True
    error: str = ""


def optimize_prompt(
    prompt: str,
    provider: str | None = None,
    model: str | None = None,
    feedback: str = "",
    temperature: float = 0.3,
) -> OptimizationResult:
    """Return an LLM-refined version of ``prompt`` + a rationale. Never raises."""
    if not (prompt or "").strip():
        return OptimizationResult(prompt, prompt, "", ok=False, error="Empty prompt.")
    feedback_block = f"Apply this feedback: {feedback}\n\n" if feedback.strip() else ""
    try:
        from langchain_core.prompts import ChatPromptTemplate

        chain = ChatPromptTemplate.from_messages(
            [("system", _OPTIMIZER_SYSTEM), ("human", _OPTIMIZER_HUMAN)]
        ) | get_chat_model(provider, model, temperature=temperature)
        raw = chain.invoke({"prompt": prompt, "feedback_block": feedback_block}).content
        improved, rationale = _parse(raw, fallback=prompt)
        return OptimizationResult(prompt, improved, rationale)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Prompt optimization failed: %s", exc)
        return OptimizationResult(prompt, prompt, "", ok=False, error=str(exc))


def _parse(raw: str, fallback: str) -> tuple[str, str]:
    text = raw or ""
    improved, rationale = fallback, ""
    if "===IMPROVED===" in text:
        rest = text.split("===IMPROVED===", 1)[1]
        if "===RATIONALE===" in rest:
            imp, rat = rest.split("===RATIONALE===", 1)
            improved, rationale = imp.strip(), rat.strip()
        else:
            improved = rest.strip()
    else:
        improved = text.strip() or fallback
    return improved, rationale
