"""Tests for the LLM response cache (BaseCache-backed, SQLite). No live LLM."""
import time

from agentx.cache import AgentXCache, cache_stats, clear_cache, enable_caching


def _gens(text: str):
    from langchain_core.outputs import Generation

    return [Generation(text=text)]


def test_cache_lookup_miss_then_hit(tmp_path):
    cache = AgentXCache(tmp_path / "c.sqlite")
    assert cache.lookup("hello", "llm::gpt-4o-mini") is None  # miss
    cache.update("hello", "llm::gpt-4o-mini", _gens("hi there"))
    got = cache.lookup("hello", "llm::gpt-4o-mini")
    assert got is not None
    assert got[0].text == "hi there"


def test_cache_stats_track_hits_and_savings(tmp_path):
    cache = AgentXCache(tmp_path / "c.sqlite")
    cache.update("q", "llm::gpt-4o-mini", _gens("a fairly long cached answer " * 5))
    cache.lookup("q", "llm::gpt-4o-mini")  # hit
    cache.lookup("nope", "llm::gpt-4o-mini")  # miss
    s = cache.stats()
    assert s["hits"] == 1 and s["misses"] == 1
    assert s["hit_rate"] == 0.5
    assert s["tokens_saved"] > 0
    assert s["est_usd_saved"] >= 0.0
    assert s["entries"] == 1


def test_cache_ttl_expiry(tmp_path):
    cache = AgentXCache(tmp_path / "c.sqlite", ttl=1)
    cache.update("k", "llm::x", _gens("v"))
    assert cache.lookup("k", "llm::x") is not None
    time.sleep(1.2)
    assert cache.lookup("k", "llm::x") is None  # expired


def test_clear_cache(tmp_path):
    p = tmp_path / "c.sqlite"
    cache = AgentXCache(p)
    cache.update("k", "llm::x", _gens("v"))
    clear_cache(p)
    assert cache_stats(p)["entries"] == 0
    assert cache.lookup("k", "llm::x") is None


def test_enable_caching_installs_global(tmp_path):
    from langchain_core.globals import get_llm_cache

    from agentx.cache import disable_caching

    cache = enable_caching(tmp_path / "c.sqlite")
    assert get_llm_cache() is cache
    disable_caching()
    assert get_llm_cache() is None
