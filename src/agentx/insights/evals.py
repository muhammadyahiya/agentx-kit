"""Prompt & response evaluation metrics.

Reusable at runtime (dashboard, notebooks, CI) — the same LLM-as-judge pattern
the generated ``evals/run_evals.py`` uses, plus deterministic metrics that need
no extra model call (length, token efficiency, latency, cost, cache hit).

    from agentx.insights import evaluate_run, judge_relevance

    metrics = evaluate_run(
        system_prompt, user_msg, response,
        provider="openai", model="gpt-4o-mini",
        latency_ms=820, criteria="Answer must mention pricing.",
    )
    print(metrics.relevance, metrics.cost_usd)
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field

from .tokens import count_tokens, estimate_cost

logger = logging.getLogger(__name__)

_JUDGE_PROMPT = (
    "You are a strict evaluator. Given a user INPUT, the assistant's OUTPUT, and "
    "the success CRITERIA, reply with ONLY a number between 0 and 1 (one decimal) "
    "for how well OUTPUT satisfies CRITERIA. If no CRITERIA is given, judge overall "
    "helpfulness and correctness.\n\n"
    "INPUT: {input}\nOUTPUT: {output}\nCRITERIA: {criteria}\nSCORE:"
)


@dataclass
class EvalMetrics:
    """Computed metrics for a single prompt/response pair."""

    relevance: float = 0.0          # 0-1 LLM-as-judge score (0 if not judged)
    length_tokens: int = 0          # output length in tokens
    token_efficiency: float = 0.0   # output tokens / input tokens
    latency_ms: int = 0
    cost_usd: float = 0.0
    cache_hit: bool = False
    judged: bool = False            # whether relevance came from a judge call

    def to_dict(self) -> dict:
        return asdict(self)


def judge_relevance(
    user_msg: str,
    response: str,
    criteria: str = "",
    *,
    provider: str | None = None,
    model: str | None = None,
    judge=None,
) -> float:
    """Score ``response`` against ``criteria`` (0-1) using an LLM judge.

    Pass a pre-built ``judge`` chat model to avoid re-instantiating it across a
    dataset; otherwise one is built from ``provider``/``model``.
    Returns 0.0 on any failure (never raises) so it's safe in a metrics loop.
    """
    try:
        if judge is None:
            from ..providers import get_chat_model
            judge = get_chat_model(provider, model)
        prompt = _JUDGE_PROMPT.format(
            input=user_msg[:4000], output=response[:4000], criteria=criteria or "(none)"
        )
        raw = judge.invoke(prompt)
        text = getattr(raw, "content", str(raw))
        match = re.search(r"(\d(?:\.\d+)?)", text or "")
        if not match:
            return 0.0
        return max(0.0, min(1.0, float(match.group(1))))
    except Exception as exc:  # noqa: BLE001 - judging must not crash the caller
        logger.warning("judge_relevance failed: %s", exc)
        return 0.0


def evaluate_run(
    prompt: str,
    user_msg: str,
    response: str,
    *,
    provider: str | None = None,
    model: str = "gpt-4o-mini",
    latency_ms: int = 0,
    criteria: str = "",
    cache_hit: bool = False,
    judge=None,
    run_judge: bool = True,
) -> EvalMetrics:
    """Compute ``EvalMetrics`` for one interaction.

    Deterministic metrics (length, efficiency, cost) are always computed.
    ``relevance`` requires an LLM call — set ``run_judge=False`` to skip it.
    """
    tokens_in = count_tokens((prompt or "") + (user_msg or ""), model)
    tokens_out = count_tokens(response or "", model)
    efficiency = round(tokens_out / tokens_in, 3) if tokens_in else 0.0
    cost = estimate_cost(tokens_in, tokens_out, model)

    relevance = 0.0
    judged = False
    if run_judge:
        relevance = judge_relevance(
            user_msg, response, criteria, provider=provider, model=model, judge=judge
        )
        judged = True

    return EvalMetrics(
        relevance=relevance,
        length_tokens=tokens_out,
        token_efficiency=efficiency,
        latency_ms=latency_ms,
        cost_usd=cost,
        cache_hit=cache_hit,
        judged=judged,
    )


@dataclass
class EvalSummary:
    """Aggregate metrics over a dataset run."""

    count: int = 0
    mean_relevance: float = 0.0
    avg_latency_ms: int = 0
    total_cost_usd: float = 0.0
    avg_token_efficiency: float = 0.0
    cache_hit_rate: float = 0.0
    per_case: list[EvalMetrics] = field(default_factory=list)


def evaluate_dataset(
    system_prompt: str,
    cases: list[dict],
    *,
    provider: str | None = None,
    model: str = "gpt-4o-mini",
    run_fn=None,
) -> EvalSummary:
    """Run each case through the model (or ``run_fn``) and aggregate metrics.

    Each case is a dict with ``input`` and optional ``criteria``.
    ``run_fn(input) -> response`` overrides the default single-call runner
    (pass your agent's ``run_text`` to evaluate the whole graph/crew).
    """
    import time

    from ..providers import get_chat_model

    llm = get_chat_model(provider, model)
    judge = get_chat_model(provider, model)

    def _default_run(text: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage
        msgs = (
            [SystemMessage(system_prompt), HumanMessage(text)]
            if system_prompt.strip()
            else [HumanMessage(text)]
        )
        resp = llm.invoke(msgs)
        return getattr(resp, "content", str(resp))

    runner = run_fn or _default_run
    results: list[EvalMetrics] = []
    for case in cases:
        user_msg = case.get("input", "")
        t0 = time.time()
        response = runner(user_msg)
        latency = int((time.time() - t0) * 1000)
        results.append(
            evaluate_run(
                system_prompt, user_msg, response,
                provider=provider, model=model, latency_ms=latency,
                criteria=case.get("criteria", ""), judge=judge,
            )
        )

    n = len(results) or 1
    return EvalSummary(
        count=len(results),
        mean_relevance=round(sum(r.relevance for r in results) / n, 3),
        avg_latency_ms=round(sum(r.latency_ms for r in results) / n),
        total_cost_usd=round(sum(r.cost_usd for r in results), 6),
        avg_token_efficiency=round(sum(r.token_efficiency for r in results) / n, 3),
        cache_hit_rate=round(sum(1 for r in results if r.cache_hit) / n, 3),
        per_case=results,
    )
