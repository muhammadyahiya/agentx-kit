"""Provider registry + factory tests (no network, no provider SDKs needed)."""
import pytest

from agentx import list_providers
from agentx.providers import ProviderError, canonical_ids, get_chat_model, get_spec


def test_registry_has_all_expected_providers():
    ids = set(canonical_ids())
    for expected in ("openai", "azure", "openrouter", "anthropic", "gemini",
                     "vertexai", "bedrock", "groq", "ollama"):
        assert expected in ids


def test_specs_are_well_formed():
    for s in list_providers():
        assert s.id and s.label and s.extra
        assert s.default_model
        assert s.crewai_prefix.endswith("/")
        assert callable(s.build_chat)


def test_aliases_resolve():
    assert get_spec("claude").id == "anthropic"
    assert get_spec("google").id == "gemini"
    assert get_spec("aws").id == "bedrock"
    assert get_spec("vertex").id == "vertexai"


def test_unknown_provider_raises():
    with pytest.raises(KeyError):
        get_spec("not-a-provider")


def test_missing_package_gives_actionable_error(monkeypatch):
    """If the provider SDK isn't installed, the error names the extra to install."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "langchain_anthropic":
            raise ImportError("no module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ProviderError) as exc:
        get_chat_model("anthropic", "claude-3-5-sonnet-latest")
    assert "agentx-kit[anthropic]" in str(exc.value)
