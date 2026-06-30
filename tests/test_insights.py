"""Tests for the prompt-insights core (token/cost, analysis, log). No live LLM."""
import pytest

from agentx.insights import (
    analyze_prompt,
    context_window,
    count_tokens,
    estimate_cost,
    get_log,
    prompt_hash,
    utilization,
)


# ----- tokens -----
def test_count_tokens_scales_with_length():
    assert count_tokens("", "gpt-4o-mini") == 0
    short = count_tokens("hello world", "gpt-4o-mini")
    long = count_tokens("hello world " * 100, "gpt-4o-mini")
    assert 0 < short < long


def test_context_window_and_utilization():
    assert context_window("gpt-4o-mini") >= 100_000
    assert context_window("totally-unknown-model") == 8192  # default
    assert 0.0 <= utilization(1000, "gpt-4o-mini") < 0.1


def test_estimate_cost_monotonic():
    cheap = estimate_cost(1000, 0, "gpt-4o-mini")
    pricey = estimate_cost(1000, 0, "gpt-4o")
    assert pricey > cheap >= 0
    assert estimate_cost(0, 0, "gpt-4o") == 0.0


# ----- analysis -----
def test_analyze_good_prompt_scores_high():
    good = (
        "You are a senior support agent. Your goal is to resolve billing issues. "
        "Respond in JSON with fields {reason, action}. Do not invent policy. "
        "Example: input: 'refund?' output: {\"reason\": \"...\", \"action\": \"...\"}."
    )
    a = analyze_prompt(good, "gpt-4o-mini")
    assert a.quality_score >= 70
    assert a.checks["has_role"] and a.checks["has_goal"] and a.checks["has_output_format"]


def test_analyze_poor_prompt_has_suggestions():
    a = analyze_prompt("do good stuff", "gpt-4o-mini")
    assert a.quality_score < 50
    assert a.suggestions
    assert a.checks["not_vague"] is False  # 'good'/'stuff' are vague


def test_analyze_long_prompt_warns():
    a = analyze_prompt("word " * 4000, "gpt-4o-mini")
    assert any("long" in w.lower() for w in a.warnings)


# ----- log -----
def test_insight_log_roundtrip(tmp_path):
    log = get_log(tmp_path / ".agentx" / "insights.jsonl")
    log.record(kind="run", model="gpt-4o-mini", tokens_in=100, tokens_out=50, cost_usd=0.001, latency_ms=420)
    log.record(kind="run", model="gpt-4o-mini", tokens_in=200, tokens_out=80, cost_usd=0.002, latency_ms=380)
    log.record(kind="optimize", model="gpt-4o-mini", tokens_in=100, tokens_out=90)
    agg = log.aggregate()
    assert agg["runs"] == 2
    assert agg["total_tokens"] == 100 + 50 + 200 + 80
    assert agg["optimizations"] == 1
    assert agg["avg_latency_ms"] == 400


def test_prompt_hash_stable():
    assert prompt_hash("abc") == prompt_hash("abc")
    assert prompt_hash("abc") != prompt_hash("abd")


# ----- dashboard launcher import is lazy/graceful -----
def test_dashboard_launch_requires_streamlit(monkeypatch):
    import builtins

    from agentx import dashboard

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "streamlit":
            raise ImportError("no streamlit")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError) as exc:
        dashboard.launch()
    assert "agentx-kit[dashboard]" in str(exc.value)
