"""Tests for AutonomousAgent + ResearchAgent (config validation, sandboxing,
result classes). Does not run actual LLM calls."""
from __future__ import annotations

from pathlib import Path

import pytest

from agentx.agents import (
    AgentResult,
    AutonomousAgent,
    AutonomousAgentConfig,
    ResearchAgent,
    ResearchAgentConfig,
    ResearchResult,
)
from agentx.agents.autonomous import _safe_join


class TestAutonomousAgentConfig:
    """Config validators for AutonomousAgent."""

    def test_valid_config(self) -> None:
        cfg = AutonomousAgentConfig(goal="Find and summarise recent RAG papers.")
        assert cfg.goal == "Find and summarise recent RAG papers."
        assert cfg.max_iterations == 20

    def test_rejects_empty_goal(self) -> None:
        with pytest.raises(ValueError, match="goal"):
            AutonomousAgentConfig(goal="")

    def test_rejects_whitespace_goal(self) -> None:
        with pytest.raises(ValueError, match="goal"):
            AutonomousAgentConfig(goal="   ")

    def test_strips_goal(self) -> None:
        cfg = AutonomousAgentConfig(goal="  research LLMs  ")
        assert cfg.goal == "research LLMs"

    def test_rejects_negative_iterations(self) -> None:
        with pytest.raises(ValueError):
            AutonomousAgentConfig(goal="test", max_iterations=-1)

    def test_rejects_zero_iterations(self) -> None:
        with pytest.raises(ValueError):
            AutonomousAgentConfig(goal="test", max_iterations=0)

    def test_rejects_out_of_range_temperature(self) -> None:
        with pytest.raises(ValueError):
            AutonomousAgentConfig(goal="test", temperature=-0.5)
        with pytest.raises(ValueError):
            AutonomousAgentConfig(goal="test", temperature=3.0)


class TestSafeJoin:
    """Verify workspace sandbox — path traversal protection."""

    def test_normal_filename(self, tmp_path: Path) -> None:
        result = _safe_join(tmp_path, "output.md")
        assert result.parent == tmp_path.resolve()
        assert result.name == "output.md"

    def test_nested_filename(self, tmp_path: Path) -> None:
        result = _safe_join(tmp_path, "sub/output.md")
        assert result.name == "output.md"

    def test_rejects_absolute_path(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="absolute"):
            _safe_join(tmp_path, "/etc/passwd")

    def test_rejects_traversal_dotdot(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="escapes workspace"):
            _safe_join(tmp_path, "../outside.txt")

    def test_rejects_deep_traversal(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="escapes workspace"):
            _safe_join(tmp_path, "../../../etc/hosts")

    def test_rejects_empty_filename(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="filename"):
            _safe_join(tmp_path, "")


class TestAutonomousAgentFactory:
    """Verify factory + workspace creation."""

    def test_workspace_is_created(self, tmp_path: Path) -> None:
        ws = tmp_path / "does_not_exist_yet"
        agent = AutonomousAgent.create(goal="test", workspace=str(ws))
        assert ws.exists()
        assert agent.workspace == ws.resolve()

    def test_default_shell_disabled(self, tmp_path: Path) -> None:
        agent = AutonomousAgent.create(goal="test", workspace=str(tmp_path))
        assert agent.config.allow_shell is False


class TestAgentResult:
    """AgentResult.__str__ must include error when success=False."""

    def test_success_str(self, tmp_path: Path) -> None:
        r = AgentResult(
            goal="test",
            summary="done",
            iterations=3,
            artifacts=[],
            success=True,
        )
        s = str(r)
        assert "✓" in s
        assert "Goal: test" in s

    def test_failure_str_includes_error(self) -> None:
        """Post Sprint 1: error field must appear in __str__."""
        r = AgentResult(
            goal="test",
            summary="",
            iterations=0,
            artifacts=[],
            success=False,
            error="LLM timeout after 120s",
        )
        s = str(r)
        assert "✗" in s
        assert "LLM timeout after 120s" in s


class TestResearchAgentConfig:
    """Config validators for ResearchAgent."""

    def test_valid_config(self) -> None:
        cfg = ResearchAgentConfig(topic="RAG frameworks 2025")
        assert cfg.topic == "RAG frameworks 2025"
        assert cfg.depth == "standard"

    def test_rejects_empty_topic(self) -> None:
        with pytest.raises(ValueError, match="topic"):
            ResearchAgentConfig(topic="")

    def test_rejects_whitespace_topic(self) -> None:
        with pytest.raises(ValueError, match="topic"):
            ResearchAgentConfig(topic="   ")

    def test_strips_topic(self) -> None:
        cfg = ResearchAgentConfig(topic="  LLMs  ")
        assert cfg.topic == "LLMs"

    def test_invalid_depth_rejected(self) -> None:
        with pytest.raises(ValueError):
            ResearchAgentConfig(topic="x", depth="ultra")  # type: ignore[arg-type]

    def test_all_valid_depths(self) -> None:
        for d in ("quick", "standard", "deep"):
            cfg = ResearchAgentConfig(topic="x", depth=d)
            assert cfg.depth == d


class TestResearchResult:
    """ResearchResult.save() must create parent directories."""

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        r = ResearchResult(
            topic="test", markdown="# Report", citations=[],
            queries_run=0, urls_visited=0, success=True,
        )
        target = tmp_path / "reports" / "deep" / "nested" / "report.md"
        r.save(target)
        assert target.exists()
        assert target.read_text() == "# Report"


class TestResearchDepthParams:
    """Verify _DEPTH_PARAMS mapping."""

    def test_all_depths_have_params(self) -> None:
        from agentx.agents.research import _DEPTH_PARAMS
        for depth in ("quick", "standard", "deep"):
            params = _DEPTH_PARAMS[depth]
            assert params["max_queries"] > 0
            assert params["max_urls"] > 0
            assert params["max_iterations"] > 0

    def test_deep_has_most_capacity(self) -> None:
        from agentx.agents.research import _DEPTH_PARAMS
        assert _DEPTH_PARAMS["deep"]["max_queries"] > _DEPTH_PARAMS["quick"]["max_queries"]
        assert _DEPTH_PARAMS["deep"]["max_urls"] > _DEPTH_PARAMS["quick"]["max_urls"]
