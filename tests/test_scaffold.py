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
    # Core + conditional files exist.
    assert (root / "pyproject.toml").exists()
    assert (root / "src/lg_bot/main.py").exists()
    assert (root / "src/lg_bot/agents.py").exists()
    assert (root / "src/lg_bot/rag.py").exists()
    assert (root / "src/lg_bot/memory.py").exists()
    assert (root / "src/lg_bot/tools.py").exists()
    assert (root / "mcp_servers.json").exists()
    assert (root / "data/skills/star-method.json").exists()
    _compile_tree(root)
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
    assert not (root / "src/crew_bot/rag.py").exists()
    assert not (root / "src/crew_bot/memory.py").exists()
    agents = (root / "src/crew_bot/agents.py").read_text()
    assert "build_crewai_agent" in agents and "build_crew" in agents
    _compile_tree(root)


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
