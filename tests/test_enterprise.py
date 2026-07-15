"""Tests for the enterprise runtime modules + enterprise scaffolding."""
import py_compile

import pytest

from agentx.guardrails import (
    GuardrailError,
    apply_guards,
    block_banned,
    default_output_guards,
    enforce_max_length,
    redact_pii,
)
from agentx.observability import setup_tracing, telemetry_enabled
from agentx.reliability import UsageLimitExceeded, UsageLimits, UsageTracker
from agentx.scaffold import ProjectSpec, generate_project
from agentx.scaffold.generator import _extras


# ----- guardrails -----
def test_redact_pii():
    r = redact_pii("reach me at a@b.com or 555-123-4567")
    assert "[REDACTED:email]" in r.text and "[REDACTED:phone]" in r.text
    assert set(r.violations) == {"pii:email", "pii:phone"}


def test_block_banned_and_length():
    assert block_banned("this is SECRET", ["secret"]).violations == ["banned:secret"]
    assert enforce_max_length("abcdef", 3).text == "abc"


def test_apply_guards_raise():
    with pytest.raises(GuardrailError):
        apply_guards("foo bar", [lambda t: block_banned(t, ["bar"])], raise_on_violation=True)


def test_output_guards_compose():
    r = apply_guards("ssn 123-45-6789 " + "x" * 99999, default_output_guards(max_chars=50))
    assert len(r.text) <= 50


# ----- usage limits -----
def test_usage_limits_tokens():
    t = UsageTracker(UsageLimits(max_total_tokens=50))
    t.record(40)
    with pytest.raises(UsageLimitExceeded):
        t.record(20)


def test_usage_limits_requests_and_cost():
    t = UsageTracker(UsageLimits(max_requests=2, price_per_1k_tokens=1.0))
    t.record(1000)
    assert t.cost_usd == 1.0
    t.record(0)
    with pytest.raises(UsageLimitExceeded):
        t.record(0)


# ----- observability opt-out -----
def test_telemetry_opt_out(monkeypatch):
    monkeypatch.setenv("AGENTX_TELEMETRY", "false")
    assert telemetry_enabled() is False
    assert setup_tracing("svc") is False  # disabled → no-op


def test_otel_sdk_disabled(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    assert telemetry_enabled() is False


# ----- enterprise scaffolding -----
def _compile_tree(root):
    for f in root.glob("**/*.py"):
        py_compile.compile(str(f), doraise=True)


def test_enterprise_extras_include_observability_and_server():
    s = ProjectSpec(name="e", provider="openai", create_venv=False)
    s.enable_enterprise()
    extras = _extras(s)
    assert "observability" in extras and "server" in extras


def test_generate_enterprise_full(tmp_path):
    s = ProjectSpec(name="ent", framework="langgraph", provider="openai", create_venv=False)
    s.enable_enterprise()
    root = generate_project(s, tmp_path / "ent", overwrite=True).target_dir
    for rel in [
        "src/ent/server.py", "src/ent/observability.py", "src/ent/guardrails.py",
        "Dockerfile", "docker-compose.yml", ".dockerignore",
        ".github/workflows/ci.yml", "evals/run_evals.py", "evals/dataset.json",
        "agentx.json",
    ]:
        assert (root / rel).exists(), f"missing {rel}"
    _compile_tree(root)
    # config.py now uses pydantic-settings
    assert "BaseSettings" in (root / "src/ent/config.py").read_text()
    # server wires FastAPI
    assert "FastAPI" in (root / "src/ent/server.py").read_text()


def test_generate_crewai_enterprise(tmp_path):
    s = ProjectSpec(name="crew-ent", framework="crewai", provider="openrouter", create_venv=False)
    s.enable_enterprise()
    root = generate_project(s, tmp_path / "crewent", overwrite=True).target_dir
    _compile_tree(root)
    assert "build_project_crew" in (root / "src/crew_ent/crew.py").read_text()
    assert "run_text" in (root / "src/crew_ent/server.py").read_text()


def test_non_enterprise_skips_files(tmp_path):
    s = ProjectSpec(name="lite", provider="openai", create_venv=False)
    root = generate_project(s, tmp_path / "lite", overwrite=True).target_dir
    assert not (root / "src/lite/server.py").exists()
    assert not (root / "Dockerfile").exists()
    assert not (root / ".github/workflows/ci.yml").exists()
