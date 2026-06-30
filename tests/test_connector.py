"""Tests for the MCP connector's recommender + project builder (no MCP transport)."""
import py_compile

from agentx.connector import build_project_from_statement, recommend_spec


# ----- recommender heuristics -----
def test_recommend_rag_support_use_case():
    rec = recommend_spec("Build a customer support agent that answers from our help docs and PDFs.")
    assert rec["framework"] == "langgraph"
    assert "rag" in rec["features"]
    assert rec["role"] == "Customer Support Agent"
    assert rec["name"]  # non-empty slug


def test_recommend_multi_agent_research():
    rec = recommend_spec("A team of agents: a researcher and a reviewer that collaborate to write reports.")
    assert rec["framework"] == "crewai"
    assert rec["agents"] >= 2


def test_recommend_production_api_enables_enterprise_features():
    rec = recommend_spec("Production-ready REST API agent, scalable with observability and monitoring.")
    for f in ("serve", "observability", "guardrails", "docker", "ci", "evals"):
        assert f in rec["features"], f


def test_recommend_minimal():
    rec = recommend_spec("just chat with me")
    assert rec["framework"] == "langgraph"
    assert rec["features"] == []


# ----- builder produces a real, compilable project -----
def test_build_project_from_statement(tmp_path):
    out = build_project_from_statement(
        "Build a support agent that answers from our documentation and serves an API.",
        output_dir=str(tmp_path / "proj"), create_venv=False, overwrite=True,
    )
    assert out["ok"] is True
    assert "rag" in out["features"] and "serve" in out["features"]
    assert "prompts.json" in out["key_files"]
    assert "agentx.json" in out["key_files"]
    # the derived system prompt carries the use case
    import json
    prompts = json.loads(out["key_files"]["prompts.json"])
    sp = next(iter(prompts["agents"].values()))["system_prompt"]
    assert "documentation" in sp.lower() or "support" in sp.lower()
    # generated python compiles
    from pathlib import Path
    for py in Path(out["target_dir"]).glob("**/*.py"):
        py_compile.compile(str(py), doraise=True)
    assert any(p.endswith("server.py") for p in out["file_tree"])


def test_build_explicit_overrides(tmp_path):
    out = build_project_from_statement(
        "chat assistant", name="my-bot", framework="crewai", provider="ollama",
        features=["memory"], output_dir=str(tmp_path / "o"), create_venv=False, overwrite=True,
    )
    assert out["name"] == "my-bot"
    assert out["framework"] == "crewai"
    assert "memory" in out["features"]


def test_client_config_shape():
    from agentx.connector import client_config

    cfg = client_config()
    assert cfg["mcpServers"]["agentx-kit"]["args"] == ["mcp"]
