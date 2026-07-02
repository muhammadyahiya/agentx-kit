"""Token counting, cost estimation, and context-window utilization.

Uses ``tiktoken`` when available for accurate counts; otherwise falls back to a
~4-chars/token heuristic. Pricing and context windows are approximate, editable
defaults — override per your contract. Cost is *derived* from tokens (the
industry convention; OTel GenAI standardises tokens, not cost).
"""
from __future__ import annotations

from dataclasses import dataclass

# Approximate context windows (tokens). Matched by substring on the model id.
_CONTEXT_WINDOWS: dict[str, int] = {
    "gpt-4o": 128_000, "gpt-4.1": 1_000_000, "gpt-4": 128_000,
    "o1": 200_000, "o3": 200_000, "o4": 200_000, "gpt-3.5": 16_385,
    # Current-generation Claude (Opus 4.x / Sonnet 4.6 / Sonnet 5 / Fable 5: 1M; Haiku 4.5: 200K).
    "claude-opus-4": 1_000_000, "claude-sonnet-5": 1_000_000, "claude-sonnet-4": 1_000_000,
    "claude-fable-5": 1_000_000, "claude-haiku-4": 200_000,
    "claude-3-5": 200_000, "claude-3": 200_000, "claude": 200_000,
    "gemini-1.5": 1_000_000, "gemini-2": 1_000_000, "gemini": 1_000_000,
    "llama-3.3": 128_000, "llama-3.1": 128_000, "llama3": 8_192, "llama": 8_192,
    "command-r": 128_000, "cohere": 128_000,
    "mixtral": 32_768, "mistral-large": 128_000, "mistral": 32_768, "qwen": 32_768,
}

# Approximate USD per 1K tokens, as (input, output). Defaults are conservative.
_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.00015, 0.0006), "gpt-4o": (0.0025, 0.01), "gpt-4.1": (0.002, 0.008),
    "gpt-4": (0.03, 0.06), "gpt-3.5": (0.0005, 0.0015),
    # Current-generation Claude pricing (per 1K tokens).
    "claude-opus-4": (0.005, 0.025), "claude-fable-5": (0.010, 0.050),
    "claude-sonnet-5": (0.003, 0.015), "claude-sonnet-4": (0.003, 0.015),
    "claude-haiku-4": (0.001, 0.005),
    "claude-3-5-sonnet": (0.003, 0.015), "claude-3-5-haiku": (0.0008, 0.004),
    "claude-3-opus": (0.015, 0.075), "claude": (0.003, 0.015),
    "gemini-1.5-flash": (0.000075, 0.0003), "gemini-1.5-pro": (0.00125, 0.005), "gemini": (0.000075, 0.0003),
    "command-r-plus": (0.0025, 0.01), "command-r": (0.00015, 0.0006), "cohere": (0.00015, 0.0006),
    "mistral-large": (0.002, 0.006), "llama": (0.0, 0.0), "qwen": (0.0, 0.0), "mistral": (0.0, 0.0),
}

_DEFAULT_WINDOW = 8_192
_DEFAULT_PRICE = (0.0, 0.0)


def _match(model: str, table: dict):
    model = (model or "").lower()
    # Longest key match wins (so "gpt-4o-mini" beats "gpt-4").
    best = None
    for key in sorted(table, key=len, reverse=True):
        if key in model:
            best = table[key]
            break
    return best


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    """Count tokens in ``text`` for ``model``. Accurate via tiktoken if installed."""
    if not text:
        return 0
    try:
        import tiktoken

        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("o200k_base" if "gpt-4o" in model or "gpt-4.1" in model else "cl100k_base")
        return len(enc.encode(text))
    except Exception:  # noqa: BLE001 - tiktoken absent or model unknown
        # ~4 chars/token heuristic with a small floor.
        return max(1, round(len(text) / 4))


def context_window(model: str) -> int:
    return _match(model, _CONTEXT_WINDOWS) or _DEFAULT_WINDOW


def utilization(tokens: int, model: str) -> float:
    """Fraction (0-1) of the model's context window used by ``tokens``."""
    win = context_window(model)
    return round(tokens / win, 4) if win else 0.0


def estimate_cost(input_tokens: int, output_tokens: int = 0, model: str = "gpt-4o-mini") -> float:
    """Estimate USD cost from token counts (approximate; pricing is editable)."""
    price_in, price_out = _match(model, _PRICING) or _DEFAULT_PRICE
    return round(input_tokens / 1000 * price_in + output_tokens / 1000 * price_out, 6)


@dataclass
class TokenReport:
    model: str
    tokens: int
    context_window: int
    utilization: float
    est_input_cost: float

    @classmethod
    def for_text(cls, text: str, model: str) -> "TokenReport":
        n = count_tokens(text, model)
        return cls(
            model=model,
            tokens=n,
            context_window=context_window(model),
            utilization=utilization(n, model),
            est_input_cost=estimate_cost(n, 0, model),
        )
