"""Tests for Sprint 3/4: catalog, new providers, evals, graphviz, domains, skills v2."""
from __future__ import annotations

import json

import pytest

from agentx.insights import EvalMetrics, evaluate_run, judge_relevance
from agentx.insights.tokens import context_window, estimate_cost
from agentx.providers import all_specs, get_spec
from agentx.providers.catalog import (
    default_index,
    embedding_models_for,
    models_for,
)
from agentx.scaffold import domains, graphviz
from agentx.skills.registry import SkillRegistry


class TestProviderCatalog:
    def test_every_provider_has_models(self) -> None:
        for spec in all_specs():
            assert models_for(spec.id), f"no catalog for {spec.id}"

    def test_anthropic_leads_with_current_model(self) -> None:
        assert models_for("anthropic")[0] == "claude-opus-4-8"

    def test_unknown_provider_returns_empty(self) -> None:
        assert models_for("does-not-exist") == []

    def test_default_index(self) -> None:
        assert default_index("anthropic", "claude-opus-4-8") == 0
        assert default_index("anthropic", "not-in-list") == 0

    def test_embedding_models(self) -> None:
        assert "BAAI/bge-small-en-v1.5" in embedding_models_for("huggingface")
        assert embedding_models_for("nope") == []


class TestNewProviders:
    def test_cohere_and_mistral_registered(self) -> None:
        ids = [s.id for s in all_specs()]
        assert "cohere" in ids
        assert "mistral" in ids

    def test_mistral_alias(self) -> None:
        assert get_spec("mistralai").id == "mistral"

    def test_anthropic_default_not_retired(self) -> None:
        # claude-3-5-sonnet-latest is retired; must be a current model.
        assert get_spec("anthropic").default_model == "claude-sonnet-4-6"


class TestTokenTables:
    def test_current_claude_context_windows(self) -> None:
        assert context_window("claude-opus-4-8") == 1_000_000
        assert context_window("claude-haiku-4-5") == 200_000

    def test_current_claude_pricing(self) -> None:
        # opus 4.8 = $5/$25 per 1M = 0.005/0.025 per 1K
        assert estimate_cost(1000, 0, "claude-opus-4-8") == pytest.approx(0.005)


class TestEvals:
    def test_deterministic_metrics_no_judge(self) -> None:
        m = evaluate_run("sys", "q", "a longer answer here", model="gpt-4o-mini",
                         latency_ms=300, run_judge=False)
        assert isinstance(m, EvalMetrics)
        assert m.length_tokens > 0
        assert m.latency_ms == 300
        assert not m.judged

    def test_judge_never_raises_without_provider(self, monkeypatch) -> None:
        # No credentials → judge returns 0.0, does not raise.
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        score = judge_relevance("q", "a", "criteria", provider="openai", model="gpt-4o-mini")
        assert score == 0.0


class TestGraphviz:
    def test_single_agent_flow(self) -> None:
        flow = graphviz.build_flow({"framework": "langgraph", "agents": ["assistant"]})
        assert ("START", "assistant") in flow.edges
        assert ("assistant", "tools") in flow.edges

    def test_supervisor_flow(self) -> None:
        flow = graphviz.build_flow(
            {"framework": "langgraph", "orchestration": "supervisor", "agents": ["a", "b"]}
        )
        assert ("START", "supervisor") in flow.edges
        assert ("supervisor", "a") in flow.edges
        assert ("a", "supervisor") in flow.edges

    def test_sequential_flow(self) -> None:
        flow = graphviz.build_flow(
            {"framework": "langgraph", "orchestration": "sequential", "agents": ["a", "b", "c"]}
        )
        assert ("START", "a") in flow.edges
        assert ("a", "b") in flow.edges
        assert ("c", "END") in flow.edges

    def test_parallel_flow(self) -> None:
        flow = graphviz.build_flow(
            {"framework": "langgraph", "orchestration": "parallel", "agents": ["a", "b"]}
        )
        assert ("a", "merge") in flow.edges
        assert ("merge", "END") in flow.edges

    def test_crewai_sequential(self) -> None:
        flow = graphviz.build_flow({"framework": "crewai", "agents": ["a", "b"]})
        assert ("START", "a") in flow.edges

    def test_mermaid_and_json(self) -> None:
        flow = graphviz.build_flow({"framework": "langgraph", "agents": ["x"]})
        assert graphviz.render_mermaid({}, flow).startswith("graph TD")
        j = graphviz.render_json({"name": "p", "agents": ["x"]}, flow)
        assert j["nodes"] and j["edges"]

    def test_load_manifest_missing(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            graphviz.load_manifest(tmp_path)

    def test_load_manifest_found(self, tmp_path) -> None:
        (tmp_path / "agentx.json").write_text(json.dumps({"name": "p", "agents": ["x"]}))
        root, mf = graphviz.load_manifest(tmp_path)
        assert root == tmp_path.resolve()
        assert mf["name"] == "p"


class TestDomains:
    def test_infer_legal(self) -> None:
        d = domains.infer_domain("legal-assistant", "review NDAs and contracts")
        assert d is not None and d.key == "legal"

    def test_infer_medical(self) -> None:
        assert domains.infer_domain("triage-bot", "patient symptom checker").key == "medical"

    def test_infer_finance(self) -> None:
        assert domains.infer_domain("portfolio-analyzer").key == "finance"

    def test_no_match_returns_none(self) -> None:
        assert domains.infer_domain("my-cool-thing", "does stuff") is None

    def test_get_domain(self) -> None:
        assert domains.get_domain("legal").label == "Legal Research Assistant"
        assert domains.get_domain("nope") is None

    def test_domain_prompts_have_guardrails(self) -> None:
        assert "not legal advice" in domains.LEGAL.system_prompt.lower()
        assert "not a substitute" in domains.MEDICAL.system_prompt.lower()


class TestSkillsV2:
    def test_add_with_tools(self, tmp_path) -> None:
        reg = SkillRegistry(tmp_path)
        s = reg.add("Citation", "Cite", "Cite [1].", tools=["web_search"], tags=["research"])
        assert s.tools == ["web_search"]
        assert s.version == "1"

    def test_backward_compat_old_json(self, tmp_path) -> None:
        (tmp_path / "old.json").write_text(json.dumps(
            {"slug": "old", "name": "Old", "description": "d", "instructions": "do x"}
        ))
        reg = SkillRegistry(tmp_path)
        old = reg.get("old")
        assert old is not None
        assert old.tools == [] and old.version == "1"

    def test_forward_compat_unknown_keys(self, tmp_path) -> None:
        (tmp_path / "f.json").write_text(json.dumps(
            {"slug": "f", "name": "F", "description": "d", "instructions": "y", "unknown": 1}
        ))
        reg = SkillRegistry(tmp_path)
        assert reg.get("f") is not None

    def test_tool_names_dedup(self, tmp_path) -> None:
        reg = SkillRegistry(tmp_path)
        reg.add("A", "d", "i", tools=["web_search", "knowledge"])
        reg.add("B", "d", "i", tools=["web_search"])
        names = reg.tool_names()
        assert names.count("web_search") == 1
        assert "knowledge" in names


class TestDomainSeedingGeneration:
    def test_generated_project_seeds_domain(self, tmp_path) -> None:
        from agentx.scaffold import ProjectSpec, generate_project

        spec = ProjectSpec(name="legal-helper", provider="openai", create_venv=False)
        result = generate_project(spec, tmp_path / "legal-helper")
        manifest = json.loads((result.target_dir / "agentx.json").read_text())
        assert manifest["domain"] == "legal"
        assert manifest["features"]["rag"] is True
        assert (result.target_dir / "knowledge" / "legal-primer.md").exists()

    def test_domain_none_stays_generic(self, tmp_path) -> None:
        from agentx.scaffold import ProjectSpec, generate_project

        spec = ProjectSpec(name="legal-helper", provider="openai", domain="none", create_venv=False)
        result = generate_project(spec, tmp_path / "legal-helper2")
        manifest = json.loads((result.target_dir / "agentx.json").read_text())
        assert manifest["domain"] is None
