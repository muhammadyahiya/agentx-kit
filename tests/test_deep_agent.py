"""Tests for agentx.agents.deep_agent — planning, filesystem, sub-agent
dispatch, reflection, and compaction primitives. Does not run actual LLM calls
except where a fake chat model is injected."""
from __future__ import annotations

from pathlib import Path

import pytest

from agentx.agents import (
    DeepAgentConfig,
    ReflectionConfig,
    SubAgentSpec,
    Todo,
)
from agentx.agents.deep_agent import (
    build_subagent_dispatcher,
    compact_messages,
    make_filesystem_tools,
    make_planning_tool,
)


class TestPlanningTool:
    def test_write_todos_records_state(self) -> None:
        tool, box = make_planning_tool()
        assert box["todos"] == []
        result = tool.invoke({"todos": [{"content": "step 1", "status": "pending"}]})
        assert "0/1" in result
        assert box["todos"] == [Todo(content="step 1", status="pending")]

    def test_write_todos_reports_completed_count(self) -> None:
        tool, box = make_planning_tool()
        tool.invoke({"todos": [
            {"content": "a", "status": "completed"},
            {"content": "b", "status": "pending"},
        ]})
        assert box["todos"][0].status == "completed"

    def test_write_todos_replaces_full_list(self) -> None:
        tool, box = make_planning_tool()
        tool.invoke({"todos": [{"content": "a", "status": "pending"}]})
        tool.invoke({"todos": [{"content": "b", "status": "pending"}]})
        assert [t.content for t in box["todos"]] == ["b"]


class TestFilesystemTools:
    def _tools(self, tmp_path: Path) -> dict:
        return {t.name: t for t in make_filesystem_tools(tmp_path)}

    def test_write_then_read(self, tmp_path: Path) -> None:
        tools = self._tools(tmp_path)
        tools["write_file"].invoke({"filename": "note.txt", "content": "hello"})
        assert tools["read_file"].invoke({"filename": "note.txt"}) == "hello"

    def test_read_missing_file(self, tmp_path: Path) -> None:
        tools = self._tools(tmp_path)
        assert "not found" in tools["read_file"].invoke({"filename": "missing.txt"})

    def test_write_rejects_path_escape(self, tmp_path: Path) -> None:
        tools = self._tools(tmp_path)
        result = tools["write_file"].invoke({"filename": "../escape.txt", "content": "x"})
        assert "Access denied" in result
        assert not (tmp_path.parent / "escape.txt").exists()

    def test_write_rejects_absolute_path(self, tmp_path: Path) -> None:
        tools = self._tools(tmp_path)
        result = tools["read_file"].invoke({"filename": "/etc/passwd"})
        assert "Access denied" in result

    def test_edit_file_replaces_text(self, tmp_path: Path) -> None:
        tools = self._tools(tmp_path)
        tools["write_file"].invoke({"filename": "a.txt", "content": "foo bar"})
        result = tools["edit_file"].invoke({"filename": "a.txt", "old_text": "foo", "new_text": "baz"})
        assert "Edited" in result
        assert tools["read_file"].invoke({"filename": "a.txt"}) == "baz bar"

    def test_edit_file_missing_old_text(self, tmp_path: Path) -> None:
        tools = self._tools(tmp_path)
        tools["write_file"].invoke({"filename": "a.txt", "content": "foo"})
        result = tools["edit_file"].invoke({"filename": "a.txt", "old_text": "nope", "new_text": "x"})
        assert "not found" in result

    def test_list_files(self, tmp_path: Path) -> None:
        tools = self._tools(tmp_path)
        tools["write_file"].invoke({"filename": "a.txt", "content": "1"})
        tools["write_file"].invoke({"filename": "sub/b.txt", "content": "2"})
        listing = tools["list_files"].invoke({})
        assert "a.txt" in listing and "sub/b.txt" in listing

    def test_list_files_empty_workspace(self, tmp_path: Path) -> None:
        tools = self._tools(tmp_path)
        assert tools["list_files"].invoke({}) == "(empty)"


class TestSubAgentDispatcher:
    def test_requires_at_least_one_spec(self) -> None:
        with pytest.raises(ValueError):
            build_subagent_dispatcher([])

    def test_dispatcher_tool_shape(self) -> None:
        specs = [
            SubAgentSpec(name="researcher", description="does research"),
            SubAgentSpec(name="writer", description="writes reports"),
        ]
        tool = build_subagent_dispatcher(specs)
        assert tool.name == "task"
        field = tool.args_schema.model_fields["subagent_type"]
        assert "researcher" in str(field.annotation) and "writer" in str(field.annotation)

    def test_unknown_subagent_type_returns_error_not_raise(self) -> None:
        specs = [SubAgentSpec(name="researcher", description="does research")]
        tool = build_subagent_dispatcher(specs)
        # Bypass the Literal validation the tool's schema would normally enforce
        # by calling the underlying function directly.
        result = tool.func("not_a_real_subagent", "do something")
        assert "Unknown subagent_type" in result


class TestReflectionConfig:
    def test_defaults(self) -> None:
        cfg = ReflectionConfig()
        assert cfg.enabled is False
        assert cfg.max_revisions == 2
        assert "APPROVE" in cfg.critic_prompt


class TestCompactMessages:
    def test_noop_when_short(self) -> None:
        from langchain_core.messages import HumanMessage

        messages = [HumanMessage("hi")]
        assert compact_messages(messages, llm=None, keep_last=6) is messages

    def test_summarises_when_over_budget(self) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        class FakeLLM:
            def invoke(self, _messages):
                return AIMessage(content="summary of the past")

        long_text = "word " * 5000
        messages = [HumanMessage(long_text) for _ in range(10)]
        result = compact_messages(messages, llm=FakeLLM(), keep_last=2, token_limit=100)
        assert len(result) == 3  # 1 summary + keep_last=2
        assert "summary" in str(result[0].content)


class TestDeepAgentConfig:
    def test_valid_config(self) -> None:
        cfg = DeepAgentConfig(goal="Audit the repo.")
        assert cfg.use_planning is True
        assert cfg.use_filesystem is True
        assert cfg.reflection.enabled is False

    def test_rejects_empty_goal(self) -> None:
        with pytest.raises(ValueError):
            DeepAgentConfig(goal="")

    def test_accepts_subagents(self) -> None:
        cfg = DeepAgentConfig(
            goal="Do the thing.",
            subagents=[SubAgentSpec(name="reviewer", description="reviews code")],
        )
        assert cfg.subagents[0].name == "reviewer"
