# Response caching (cost & latency saver)

Caching is the top 2026 token-optimization lever. Turn on a **global LLM response cache** and
every provider call is served from a local store on repeat — no code changes:

```python
from agentx import enable_caching, cache_stats
enable_caching()                 # all get_chat_model(...) calls are cached
...
print(cache_stats())             # {'hit_rate': 0.6, 'tokens_saved': 12000, 'est_usd_saved': 0.024, ...}
```

```bash
agentx cache stats               # hit rate + estimated tokens/$ saved
agentx cache clear
```

Generated projects can enable it automatically (it's part of `--enterprise`), and the
**dashboard's Trends tab shows live hit-rate and $ saved**. TTL-capable, SQLite-backed at
`.agentx/llm_cache.sqlite`.

See [`agentx cache`](../cli/cache.md) for the CLI flags.
