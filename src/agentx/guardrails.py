"""Guardrails: input/output validation, PII redaction, and content checks.

Lightweight, dependency-free defaults that cover the common enterprise asks
(PII redaction, banned content, length caps). Compose your own by passing
callables to :func:`apply_guards`. For heavier needs (jailbreak/moderation),
wire in Guardrails-AI or NeMo Guardrails in your project.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_PII_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
}


class GuardrailError(ValueError):
    """Raised by a guard when input/output is rejected outright."""

@dataclass
class GuardResult:
    text: str
    violations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def redact_pii(text: str, kinds: tuple[str, ...] | None = None) -> GuardResult:
    """Replace detected PII with ``[REDACTED:<kind>]``."""
    out = text
    found: list[str] = []
    for kind, pattern in _PII_PATTERNS.items():
        if kinds and kind not in kinds:
            continue
        if pattern.search(out):
            found.append(f"pii:{kind}")
            out = pattern.sub(f"[REDACTED:{kind}]", out)
    return GuardResult(out, found)


def block_banned(text: str, banned: list[str]) -> GuardResult:
    lowered = text.lower()
    hits = [w for w in banned if w.lower() in lowered]
    return GuardResult(text, [f"banned:{w}" for w in hits])


def enforce_max_length(text: str, max_chars: int) -> GuardResult:
    if len(text) > max_chars:
        return GuardResult(text[:max_chars], [f"truncated:{len(text)}>{max_chars}"])
    return GuardResult(text)


def apply_guards(text: str, guards: list, raise_on_violation: bool = False) -> GuardResult:
    """Run guards in order, threading the (possibly transformed) text through.

    Each guard is a callable ``str -> GuardResult``. Violations accumulate.
    """
    violations: list[str] = []
    current = text
    for guard in guards:
        result = guard(current)
        current = result.text
        violations.extend(result.violations)
    if violations and raise_on_violation:
        raise GuardrailError("; ".join(violations))
    return GuardResult(current, violations)


def default_input_guards(banned: list[str] | None = None, max_chars: int = 8000) -> list:
    return [
        lambda t: enforce_max_length(t, max_chars),
        lambda t: block_banned(t, banned or []),
    ]


def default_output_guards(redact: bool = True, max_chars: int = 16000) -> list:
    # Redact first, then cap length last so max_chars is the final guarantee.
    guards = []
    if redact:
        guards.append(lambda t: redact_pii(t))
    guards.append(lambda t: enforce_max_length(t, max_chars))
    return guards
