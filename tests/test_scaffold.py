"""Scaffolder tests: spec, generator rendering, and generated-code validity."""
import py_compile

import pytest

from agentx.scaffold import AgentSpec, ProjectSpec, generate_project
from agentx.scaffold.generator import _extras


def _spec(**kw) -> ProjectSpec:
    base = dict(name="My Bot", provider="openai", framework="langgraph", create_venv=False)
    base.update(kw)
    return ProjectSpec(**base)


def test_spec_derives_package_and_slug():
    s = _spec(name="My Cool Agent")
    assert s.package == "my_cool_agent"
    assert s.slug == "my-cool-agent"


def test_extras_reflect_features():
    s = _spec(provider="bedrock", framework="crewai", use_rag=True, use_mcp=True)
    extras = _extras(s)
    assert "bedrock" in extras and "crewai" in extras
    assert "rag" in extras and "mcp" in extras


def _compile_tree(root):
    """py_compile every generated .py file (syntax check, no imports executed)."""
    files = list(root.glob("**/*.py"))
    assert files, "no python files generated"
    for f in files:
        py_compile.compile(str(f), doraise=True)
    return files


def test_generate_langgraph_full(tmp_path):
    s = _spec(
        name="lg-bot", framework="langgraph", provider="openai",
        agents=[AgentSpec(name="researcher", system_prompt="You research deeply."),
                AgentSpec(name="writer")],
        use_rag=True, memory="both", use_mcp=True, use_skills=True,
    )
    result = generate_project(s, tmp_path / "lg", overwrite=True)
    root = result.target_dir
    # Core + conditional files exist — real LangGraph structure.
    assert (root / "pyproject.toml").exists()
    assert (root / "src/lg_bot/main.py").exists()
    assert (root / "src/lg_bot/graph.py").exists()
    # Structured folder layout (state/ schemas/ prompts/ nodes/ utils/ libs/).
    assert (root / "src/lg_bot/state/__init__.py").exists()
    assert (root / "src/lg_bot/schemas/__init__.py").exists()
    assert (root / "src/lg_bot/prompts/__init__.py").exists()
    assert (root / "src/lg_bot/utils/tools.py").exists()
    assert (root / "src/lg_bot/utils/llm.py").exists()
    assert (root / "src/lg_bot/utils/rag.py").exists()
    assert (root / "src/lg_bot/utils/retriever.py").exists()
    assert (root / "src/lg_bot/libs/agent_factory.py").exists()
    # One node module per agent (multi-agent → supervisor router too).
    assert (root / "src/lg_bot/nodes/researcher.py").exists()
    assert (root / "src/lg_bot/nodes/writer.py").exists()
    assert (root / "src/lg_bot/nodes/supervisor.py").exists()
    assert (root / "src/lg_bot/memory.py").exists()
    assert (root / "mcp_servers.json").exists()
    assert (root / "data/skills/star-method.json").exists()
    _compile_tree(root)
    # The graph uses real langgraph/langchain APIs (not just a wrapper).
    graph = (root / "src/lg_bot/graph.py").read_text()
    assert "StateGraph" in graph and "from langgraph.graph import" in graph
    state = (root / "src/lg_bot/state/__init__.py").read_text()
    assert "add_messages" in state and "TypedDict" in state
    # pyproject wires the right extras + script.
    pyproject = (root / "pyproject.toml").read_text()
    assert "agentx-kit[" in pyproject and "langgraph" in pyproject and "rag" in pyproject
    assert "lg-bot = " in pyproject
    # Prompts are externalised into prompts.json (data-driven, editable post-gen).
    import json
    data = json.loads((root / "prompts.json").read_text())
    assert set(data["agents"]) == {"researcher", "writer"}
    assert data["agents"]["researcher"]["system_prompt"] == "You research deeply."
    assert data["with_rag"] is True


def test_generate_crewai_minimal(tmp_path):
    s = _spec(name="crew-bot", framework="crewai", provider="openrouter", memory="none")
    result = generate_project(s, tmp_path / "crew", overwrite=True)
    root = result.target_dir
    assert not (root / "src/crew_bot/utils/rag.py").exists()
    assert not (root / "src/crew_bot/memory.py").exists()
    # Real CrewAI structure: agents + tasks + crew.
    assert "build_crewai_agent" in (root / "src/crew_bot/agents.py").read_text()
    assert "Task" in (root / "src/crew_bot/tasks.py").read_text()
    crew = (root / "src/crew_bot/crew.py").read_text()
    assert "build_crew" in crew and "build_project_crew" in crew
    _compile_tree(root)


@pytest.mark.parametrize("orchestration", ["supervisor", "sequential", "parallel"])
def test_generate_orchestration_variants_compile(tmp_path, orchestration):
    s = _spec(
        name=f"orch-{orchestration}", framework="langgraph",
        agents=[AgentSpec(name="alpha"), AgentSpec(name="beta")],
        orchestration=orchestration,
    )
    root = generate_project(s, tmp_path / orchestration, overwrite=True).target_dir
    pkg = f"orch_{orchestration}"
    assert (root / f"src/{pkg}/nodes/alpha.py").exists()
    assert (root / f"src/{pkg}/nodes/beta.py").exists()
    assert (root / f"src/{pkg}/nodes/supervisor.py").exists() == (orchestration == "supervisor")
    graph = (root / f"src/{pkg}/graph.py").read_text()
    assert "build_graph" in graph
    _compile_tree(root)


def test_generate_voice_subagents_claw_streamlit(tmp_path):
    s = _spec(
        name="rich-bot", framework="langgraph",
        agents=[AgentSpec(name="assistant")],
        use_voice=True, use_subagents=True, claw=True, streamlit=True, serve=True,
    )
    root = generate_project(s, tmp_path / "rich", overwrite=True).target_dir
    assert (root / "src/rich_bot/libs/voice.py").exists()
    assert (root / "src/rich_bot/claw/webhook.py").exists()
    assert (root / "src/rich_bot/claw/intent.py").exists()
    assert (root / "streamlit_app.py").exists()
    # Sub-agent wiring is present in tool assembly.
    tools = (root / "src/rich_bot/utils/tools.py").read_text()
    assert "make_subagent_tool" in tools and "get_subagent_tools" in tools
    # Server mounts the claw router.
    assert "claw_router" in (root / "src/rich_bot/server.py").read_text()
    _compile_tree(root)
    # Manifest records the new features.
    import json
    feats = json.loads((root / "agentx.json").read_text())["features"]
    assert feats["voice"] and feats["subagents"] and feats["claw"] and feats["streamlit"]


def test_nodes_build_lazily_not_at_import(tmp_path):
    """Regression: worker/sub-agent construction must be lazy so `import graph`
    never builds models or fails on a missing provider dep."""
    s = _spec(
        name="lazy-bot", framework="langgraph",
        agents=[AgentSpec(name="alpha"), AgentSpec(name="beta")],
        orchestration="supervisor", use_subagents=True,
    )
    root = generate_project(s, tmp_path / "lazy", overwrite=True).target_dir
    factory = (root / "src/lazy_bot/libs/agent_factory.py").read_text()
    # The model/tools are resolved inside a nested lazy helper, not eagerly.
    assert "def _agent(" in factory
    # A worker module must not call get_tools()/make_worker eagerly build a model:
    worker = (root / "src/lazy_bot/nodes/alpha.py").read_text()
    assert "make_worker(" in worker  # node is declared, but the agent builds on first call
    _compile_tree(root)


def test_stream_text_filters_non_ai_messages(tmp_path):
    """Regression: SSE streaming must only emit AI tokens, never tool messages
    (so tool errors like 'Access denied' don't leak to users)."""
    s = _spec(
        name="stream-bot", framework="langgraph",
        agents=[AgentSpec(name="alpha"), AgentSpec(name="beta")],
        orchestration="supervisor", use_mcp=True,
    )
    root = generate_project(s, tmp_path / "stream", overwrite=True).target_dir
    graph = (root / "src/stream_bot/graph.py").read_text()
    assert "AIMessageChunk" in graph
    assert "isinstance(chunk, (AIMessage, AIMessageChunk))" in graph


def test_extras_include_voice_and_streamlit():
    s = _spec(use_voice=True, streamlit=True, claw=True)
    extras = _extras(s)
    assert "voice" in extras and "streamlit" in extras


def test_generate_refuses_nonempty_dir(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "keep.txt").write_text("hi")
    with pytest.raises(FileExistsError):
        generate_project(_spec(), tmp_path / "x")


def test_env_example_lists_provider_vars(tmp_path):
    s = _spec(name="azbot", provider="azure")
    result = generate_project(s, tmp_path / "az", overwrite=True)
    env = (result.target_dir / ".env.example").read_text()
    assert "AZURE_OPENAI_API_KEY" in env
    assert "AGENTX_PROVIDER=azure" in env
